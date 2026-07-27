"""Historical name/ST normalization and daily tradability projection."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import duckdb


class DuckDBHistoricalStatusProjector:
    def compact_name_history(
        self,
        *,
        source_files: tuple[Path, ...],
        output: Path,
        imported_at: datetime,
    ) -> dict[str, int]:
        if not source_files:
            raise ValueError("旧发布缺少 namechange 数据")
        output.parent.mkdir(parents=True, exist_ok=True)
        temporary = output.with_suffix(".parquet.tmp")
        temporary.unlink(missing_ok=True)
        target = _literal(temporary)
        with duckdb.connect(":memory:") as connection:
            connection.execute(
                f"""
                COPY (
                    WITH source AS (
                        SELECT *,
                               lead(start_date) OVER (
                                   PARTITION BY ts_code ORDER BY start_date, "name"
                               ) AS next_start
                        FROM read_parquet(?)
                    ),
                    normalized AS (
                        SELECT
                            'tushare' AS provider,
                            'legacy-astramind-silver/namechange' AS source_endpoint,
                            CAST(? AS TIMESTAMPTZ) AS retrieved_at,
                            timezone(
                                'Asia/Shanghai',
                                CAST(start_date AS TIMESTAMP) + INTERVAL '18 hours'
                            ) AS available_at,
                            '1.0.0' AS schema_version,
                            'sha256:' || sha256(
                                coalesce(_raw_sha256, '') || '|' || ts_code || '|' ||
                                CAST(start_date AS VARCHAR) || '|' || "name"
                            ) AS source_record_hash,
                            ts_code AS instrument_id,
                            trim("name") AS name,
                            start_date AS effective_start_date,
                            CASE
                                WHEN next_start IS NULL THEN end_date
                                WHEN end_date IS NULL THEN next_start - INTERVAL 1 DAY
                                ELSE least(end_date, next_start - INTERVAL 1 DAY)
                            END::DATE AS effective_end_date,
                            end_date AS provider_end_date,
                            ann_date AS announced_on,
                            trim(change_reason) AS change_reason,
                            CASE
                                WHEN upper(trim("name")) LIKE '*ST%' THEN 'star_st'
                                WHEN upper(trim("name")) LIKE 'ST%'
                                  OR upper(trim("name")) LIKE 'SST%' THEN 'st'
                                WHEN upper(trim("name")) LIKE 'PT%' THEN 'pt'
                                WHEN trim(change_reason) IN (
                                    '退市整理期', '高风险警示', '叠加ST'
                                ) THEN 'high_risk'
                                ELSE 'normal'
                            END AS risk_status
                        FROM source
                    )
                    SELECT *,
                           risk_status <> 'normal' AS is_special_treatment
                    FROM normalized
                    ORDER BY instrument_id, effective_start_date, name
                ) TO '{target}' (FORMAT PARQUET, COMPRESSION ZSTD)
                """,
                [[str(path) for path in source_files], imported_at],
            )
            row = connection.execute(
                """
                SELECT count(*) AS rows,
                       count(DISTINCT instrument_id) AS instruments,
                       count_if(provider_end_date IS DISTINCT FROM effective_end_date)
                           AS adjusted_intervals,
                       count_if(is_special_treatment) AS special_treatment_rows
                FROM read_parquet(?)
                """,
                [str(temporary)],
            ).fetchone()
        assert row is not None
        temporary.replace(output)
        return dict(
            zip(
                ("rows", "instruments", "adjusted_intervals", "special_treatment_rows"),
                map(int, row),
                strict=True,
            )
        )

    def project_year(
        self,
        *,
        year: int,
        security_master: Path,
        trade_calendar: Path,
        daily_files: tuple[Path, ...],
        price_limit_files: tuple[Path, ...],
        suspension_files: tuple[Path, ...],
        name_history: Path,
        output: Path,
        imported_at: datetime,
    ) -> dict[str, int]:
        if not daily_files:
            raise ValueError(f"{year} 年缺少日线分区")
        output.parent.mkdir(parents=True, exist_ok=True)
        temporary = output.with_suffix(".parquet.tmp")
        temporary.unlink(missing_ok=True)
        with duckdb.connect(":memory:") as connection:
            _create_optional_views(connection, price_limit_files, suspension_files)
            connection.execute(
                _projection_sql(temporary),
                [
                    [str(path) for path in daily_files],
                    str(trade_calendar),
                    year,
                    str(security_master),
                    str(name_history),
                    imported_at,
                ],
            )
            row = connection.execute(_stats_sql(), [str(temporary)]).fetchone()
        assert row is not None
        temporary.replace(output)
        keys = (
            "rows",
            "instruments",
            "unknown_name_rows",
            "unknown_name_instruments",
            "special_treatment_rows",
            "rows_with_daily_bar",
            "confirmed_suspended_rows",
            "ambiguous_event_rows",
            "unknown_no_bar_rows",
            "missing_limit_rows",
            "unusable_limit_rows",
            "upper_limit_locked_rows",
            "lower_limit_locked_rows",
        )
        return dict(zip(keys, map(int, row), strict=True))


def _create_optional_views(
    connection: duckdb.DuckDBPyConnection,
    price_files: tuple[Path, ...],
    suspension_files: tuple[Path, ...],
) -> None:
    if price_files:
        connection.execute(
            f"CREATE VIEW limits AS SELECT * FROM read_parquet({_path_list(price_files)})"
        )
    else:
        connection.execute(
            """
            CREATE VIEW limits AS
            SELECT NULL::VARCHAR instrument_id, NULL::DATE trade_date,
                   NULL::DOUBLE upper_limit, NULL::DOUBLE lower_limit,
                   NULL::BOOLEAN limit_prices_usable WHERE false
            """
        )
    if suspension_files:
        connection.execute(
            f"CREATE VIEW events AS SELECT * FROM read_parquet({_path_list(suspension_files)})"
        )
    else:
        connection.execute(
            """
            CREATE VIEW events AS
            SELECT NULL::VARCHAR instrument_id, NULL::DATE trade_date,
                   NULL::VARCHAR suspension_type, NULL::VARCHAR suspension_timing
            WHERE false
            """
        )


def _projection_sql(output: Path) -> str:
    target = _literal(output)
    return f"""
    COPY (
      WITH bars AS (
        SELECT instrument_id, trade_date, high, low FROM read_parquet(?)
      ), sessions AS (
        SELECT DISTINCT calendar_date AS trade_date
        FROM read_parquet(?) WHERE is_open AND year(calendar_date) = ?
      ), listed AS (
        SELECT s.instrument_id, d.trade_date
        FROM read_parquet(?) s CROSS JOIN sessions d
        WHERE s.list_date <= d.trade_date
          AND (s.delist_date IS NULL OR s.delist_date >= d.trade_date)
      ), event_state AS (
        SELECT instrument_id, trade_date, count(*) AS event_count,
               bool_or(
                   suspension_type = 'S' AND (
                       suspension_timing IS NULL OR trim(suspension_timing) = ''
                       OR trim(suspension_timing) = '09:30-15:00'
                   )
               ) AS full_day_s,
               bool_or(suspension_type = 'R') AS has_resume
        FROM events GROUP BY instrument_id, trade_date
      ), joined AS (
        SELECT g.*, n.name, n.risk_status, n.is_special_treatment,
               b.instrument_id IS NOT NULL AS has_bar, b.high, b.low,
               l.upper_limit, l.lower_limit, l.limit_prices_usable,
               coalesce(e.event_count, 0) AS event_count,
               coalesce(e.full_day_s, false) AS full_day_s,
               coalesce(e.has_resume, false) AS has_resume
        FROM listed g
        LEFT JOIN read_parquet(?) n
          ON n.instrument_id = g.instrument_id
         AND g.trade_date >= n.effective_start_date
         AND (n.effective_end_date IS NULL OR g.trade_date <= n.effective_end_date)
        LEFT JOIN bars b
          ON b.instrument_id = g.instrument_id AND b.trade_date = g.trade_date
        LEFT JOIN limits l
          ON l.instrument_id = g.instrument_id AND l.trade_date = g.trade_date
        LEFT JOIN event_state e
          ON e.instrument_id = g.instrument_id AND e.trade_date = g.trade_date
      ), states AS (
        SELECT *,
          CASE
            WHEN has_bar AND event_count > 0 THEN 'event_with_bar'
            WHEN NOT has_bar AND full_day_s AND NOT has_resume THEN 'suspended'
            WHEN NOT has_bar AND event_count > 0 THEN 'ambiguous_event'
            WHEN NOT has_bar THEN 'unknown_no_bar'
            ELSE 'no_event'
          END AS suspension_state,
          CASE
            WHEN limit_prices_usable IS NULL THEN 'missing'
            WHEN NOT limit_prices_usable THEN 'unusable'
            ELSE 'usable'
          END AS price_limit_state
        FROM joined
      )
      SELECT
        'derived' AS provider,
        'daily-tradability-projection' AS source_endpoint,
        CAST(? AS TIMESTAMPTZ) AS retrieved_at,
        timezone('Asia/Shanghai', CAST(trade_date AS TIMESTAMP) + INTERVAL '18 hours')
          AS available_at,
        '1.0.0' AS schema_version,
        'sha256:' || sha256(
          instrument_id || '|' || CAST(trade_date AS VARCHAR) || '|' ||
          coalesce(name, '') || '|' || coalesce(risk_status, 'unknown') || '|' ||
          suspension_state || '|' || price_limit_state
        ) AS source_record_hash,
        instrument_id, trade_date, name AS historical_name,
        coalesce(risk_status, 'unknown') AS risk_status,
        is_special_treatment,
        CASE
          WHEN risk_status IS NULL THEN 'unknown_name_status'
          WHEN is_special_treatment THEN 'excluded_special_treatment'
          ELSE 'eligible'
        END AS research_eligibility,
        has_bar AS has_daily_bar, suspension_state, price_limit_state,
        CASE WHEN has_bar AND price_limit_state = 'usable'
          THEN low >= upper_limit ELSE NULL END AS upper_limit_locked,
        CASE WHEN has_bar AND price_limit_state = 'usable'
          THEN high <= lower_limit ELSE NULL END AS lower_limit_locked,
        CASE
          WHEN suspension_state = 'suspended' THEN 'suspended'
          WHEN NOT has_bar THEN 'no_bar'
          WHEN price_limit_state <> 'usable' THEN 'unknown_limit'
          WHEN low >= upper_limit THEN 'limit_locked'
          ELSE 'tradable'
        END AS buy_state,
        CASE
          WHEN suspension_state = 'suspended' THEN 'suspended'
          WHEN NOT has_bar THEN 'no_bar'
          WHEN price_limit_state <> 'usable' THEN 'unknown_limit'
          WHEN high <= lower_limit THEN 'limit_locked'
          ELSE 'tradable'
        END AS sell_state
      FROM states ORDER BY trade_date, instrument_id
    ) TO '{target}' (FORMAT PARQUET, COMPRESSION ZSTD)
    """


def _stats_sql() -> str:
    return """
    SELECT count(*), count(DISTINCT instrument_id),
           coalesce(count_if(risk_status = 'unknown'), 0),
           count(DISTINCT instrument_id) FILTER (risk_status = 'unknown'),
           coalesce(count_if(is_special_treatment), 0),
           coalesce(count_if(has_daily_bar), 0),
           coalesce(count_if(suspension_state = 'suspended'), 0),
           coalesce(count_if(suspension_state = 'ambiguous_event'), 0),
           coalesce(count_if(suspension_state = 'unknown_no_bar'), 0),
           coalesce(count_if(price_limit_state = 'missing'), 0),
           coalesce(count_if(price_limit_state = 'unusable'), 0),
           coalesce(count_if(upper_limit_locked), 0),
           coalesce(count_if(lower_limit_locked), 0)
    FROM read_parquet(?)
    """


def _literal(path: Path) -> str:
    return str(path).replace("'", "''")


def _path_list(paths: tuple[Path, ...]) -> str:
    return "[" + ",".join(f"'{_literal(path)}'" for path in paths) + "]"


__all__ = ["DuckDBHistoricalStatusProjector"]
