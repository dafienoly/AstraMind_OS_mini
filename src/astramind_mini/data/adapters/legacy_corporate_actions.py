"""Normalize dividend facts and derive snapshot-bound adjusted research prices."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import duckdb


class DuckDBCorporateActionProjector:
    def compact_actions(
        self,
        *,
        source_files: tuple[Path, ...],
        output: Path,
        imported_at: datetime,
    ) -> dict[str, int]:
        if not source_files:
            raise ValueError("旧发布缺少 dividend 数据")
        output.parent.mkdir(parents=True, exist_ok=True)
        temporary = output.with_suffix(".parquet.tmp")
        temporary.unlink(missing_ok=True)
        with duckdb.connect(":memory:") as connection:
            connection.execute(
                _ACTION_SQL.format(target=_literal(temporary)),
                [imported_at, imported_at, [str(path) for path in source_files]],
            )
            row = connection.execute(
                """
                SELECT count(*), count(DISTINCT provider_record_hash),
                       count(DISTINCT instrument_id),
                       count_if(is_implemented),
                       count_if(NOT availability_known),
                       count_if(is_implemented AND ex_date IS NOT NULL)
                FROM read_parquet(?)
                """,
                [str(temporary)],
            ).fetchone()
        assert row is not None
        if row[0] != row[1]:
            temporary.unlink(missing_ok=True)
            raise ValueError("公司行为提供方记录身份重复")
        temporary.replace(output)
        keys = (
            "rows",
            "unique_records",
            "instruments",
            "implemented_rows",
            "unknown_availability_rows",
            "implemented_ex_date_rows",
        )
        return dict(zip(keys, map(int, row), strict=True))

    def build_factor_anchors(
        self,
        *,
        factor_files: tuple[Path, ...],
        output: Path,
    ) -> dict[str, int]:
        if not factor_files:
            raise ValueError("基础快照缺少复权因子")
        output.parent.mkdir(parents=True, exist_ok=True)
        temporary = output.with_suffix(".parquet.tmp")
        temporary.unlink(missing_ok=True)
        with duckdb.connect(":memory:") as connection:
            connection.execute(
                f"""
                COPY (
                  SELECT instrument_id, trade_date AS terminal_factor_date,
                         adjustment_factor AS terminal_adjustment_factor
                  FROM read_parquet(?)
                  QUALIFY row_number() OVER (
                    PARTITION BY instrument_id ORDER BY trade_date DESC
                  ) = 1
                  ORDER BY instrument_id
                ) TO '{_literal(temporary)}' (FORMAT PARQUET, COMPRESSION ZSTD)
                """,
                [[str(path) for path in factor_files]],
            )
            row = connection.execute(
                "SELECT count(*), count_if(terminal_adjustment_factor <= 0) FROM read_parquet(?)",
                [str(temporary)],
            ).fetchone()
        assert row is not None
        if row[1]:
            temporary.unlink(missing_ok=True)
            raise ValueError("终端复权因子包含非正值")
        temporary.replace(output)
        return {"rows": int(row[0]), "invalid_rows": int(row[1])}

    def project_year(
        self,
        *,
        daily_files: tuple[Path, ...],
        factor_files: tuple[Path, ...],
        action_history: Path,
        factor_anchors: Path,
        previous_index_anchors: Path | None,
        output: Path,
        next_index_anchors: Path,
        imported_at: datetime,
    ) -> dict[str, int]:
        if not daily_files or not factor_files:
            raise ValueError("年度复权投影缺少日线或复权因子")
        output.parent.mkdir(parents=True, exist_ok=True)
        next_index_anchors.parent.mkdir(parents=True, exist_ok=True)
        temporary = output.with_suffix(".parquet.tmp")
        anchor_temporary = next_index_anchors.with_suffix(".parquet.tmp")
        temporary.unlink(missing_ok=True)
        anchor_temporary.unlink(missing_ok=True)
        with duckdb.connect(":memory:") as connection:
            _index_anchor_view(connection, previous_index_anchors)
            connection.execute(
                _ADJUSTED_SQL.format(target=_literal(temporary)),
                [
                    [str(path) for path in daily_files],
                    [str(path) for path in factor_files],
                    str(factor_anchors),
                    str(action_history),
                    imported_at,
                ],
            )
            row = connection.execute(_STATS_SQL, [str(temporary)]).fetchone()
            connection.execute(
                _NEXT_ANCHOR_SQL.format(target=_literal(anchor_temporary)),
                [str(temporary)],
            )
        assert row is not None
        temporary.replace(output)
        anchor_temporary.replace(next_index_anchors)
        keys = (
            "rows",
            "unique_rows",
            "factor_change_rows",
            "factor_changes_with_action",
            "factor_return_error_over_1bp",
            "invalid_research_price_rows",
        )
        return dict(zip(keys, map(int, row), strict=True))


_ACTION_SQL = """
COPY (
  SELECT
    'tushare' AS provider,
    'legacy-astramind-silver/dividend' AS source_endpoint,
    CAST(? AS TIMESTAMPTZ) AS retrieved_at,
    CASE WHEN ann_date IS NULL THEN CAST(? AS TIMESTAMPTZ)
      ELSE timezone(
        'Asia/Shanghai', CAST(ann_date AS TIMESTAMP) + INTERVAL '18 hours'
      ) END AS available_at,
    '1.0.0' AS schema_version,
    'sha256:' || record_hash AS source_record_hash,
    ts_code AS instrument_id,
    end_date AS reporting_period,
    ann_date AS announced_on,
    ann_date IS NOT NULL AS availability_known,
    trim(div_proc) AS process_status,
    CASE
      WHEN coalesce(stk_div, 0) > 0
       AND greatest(coalesce(cash_div, 0), coalesce(cash_div_tax, 0)) > 0
        THEN 'cash_and_stock'
      WHEN coalesce(stk_div, 0) > 0 THEN 'stock'
      WHEN greatest(coalesce(cash_div, 0), coalesce(cash_div_tax, 0)) > 0 THEN 'cash'
      ELSE 'unspecified'
    END AS action_kind,
    stk_div AS stock_dividend_per_share,
    cash_div AS cash_dividend_pre_tax_per_share,
    cash_div_tax AS cash_dividend_after_tax_per_share,
    record_date, ex_date, pay_date AS payment_date, base_date,
    base_share AS base_shares_ten_thousand,
    'sha256:' || record_hash AS provider_record_hash,
    trim(div_proc) = '实施' AS is_implemented
  FROM read_parquet(?)
  ORDER BY instrument_id, reporting_period, announced_on, provider_record_hash
) TO '{target}' (FORMAT PARQUET, COMPRESSION ZSTD)
"""


_ADJUSTED_SQL = """
COPY (
WITH source AS (
  SELECT d.instrument_id, d.trade_date,
         d.open AS raw_open, d.high AS raw_high, d.low AS raw_low,
         d.close AS raw_close, d.percent_change / 100.0 AS reported_total_return,
         f.adjustment_factor, t.terminal_adjustment_factor, t.terminal_factor_date,
         p.research_close_index AS base_index,
         p.last_raw_close AS anchor_raw_close,
         p.last_adjustment_factor AS anchor_factor,
         p.last_trade_date AS anchor_trade_date,
         row_number() OVER (
           PARTITION BY d.instrument_id ORDER BY d.trade_date
         ) AS row_number
  FROM read_parquet(?) d
  JOIN read_parquet(?) f USING (instrument_id, trade_date)
  JOIN read_parquet(?) t USING (instrument_id)
  LEFT JOIN prior_index_anchor p USING (instrument_id)
), previous AS (
  SELECT *,
    coalesce(
      lag(raw_close) OVER (PARTITION BY instrument_id ORDER BY trade_date),
      anchor_raw_close
    ) AS previous_raw_close,
    coalesce(
      lag(adjustment_factor) OVER (PARTITION BY instrument_id ORDER BY trade_date),
      anchor_factor
    ) AS previous_factor,
    coalesce(
      lag(trade_date) OVER (PARTITION BY instrument_id ORDER BY trade_date),
      anchor_trade_date
    ) AS previous_trade_date
  FROM source
), indexed AS (
  SELECT *,
    coalesce(base_index, 1.0) * exp(sum(
      CASE WHEN base_index IS NULL AND row_number = 1 THEN 0.0
           ELSE ln(1.0 + reported_total_return) END
    ) OVER (
      PARTITION BY instrument_id ORDER BY trade_date
      ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    )) AS research_close_index
  FROM previous
), derived AS (
  SELECT *,
    CASE WHEN previous_raw_close IS NULL THEN NULL ELSE
      raw_close * adjustment_factor
      / nullif(previous_raw_close * previous_factor, 0) - 1
    END AS factor_implied_return,
    previous_factor IS NOT NULL
      AND abs(adjustment_factor - previous_factor) > 1e-12 AS factor_changed,
    EXISTS (
      SELECT 1 FROM read_parquet(?) a
      WHERE a.instrument_id = indexed.instrument_id
        AND a.is_implemented AND a.availability_known
        AND a.ex_date > indexed.previous_trade_date
        AND a.ex_date <= indexed.trade_date
    ) AS has_implemented_action_evidence
  FROM indexed
)
SELECT
  'derived' AS provider,
  'snapshot-adjusted-market' AS source_endpoint,
  CAST(? AS TIMESTAMPTZ) AS retrieved_at,
  timezone('Asia/Shanghai', CAST(trade_date AS TIMESTAMP) + INTERVAL '18 hours')
    AS available_at,
  '1.0.0' AS schema_version,
  'sha256:' || sha256(
    instrument_id || '|' || CAST(trade_date AS VARCHAR) || '|' ||
    CAST(raw_close AS VARCHAR) || '|' || CAST(adjustment_factor AS VARCHAR) || '|' ||
    CAST(terminal_adjustment_factor AS VARCHAR)
  ) AS source_record_hash,
  instrument_id, trade_date, raw_open, raw_high, raw_low, raw_close,
  adjustment_factor, terminal_adjustment_factor, terminal_factor_date,
  raw_open * adjustment_factor / terminal_adjustment_factor AS forward_adjusted_open,
  raw_high * adjustment_factor / terminal_adjustment_factor AS forward_adjusted_high,
  raw_low * adjustment_factor / terminal_adjustment_factor AS forward_adjusted_low,
  raw_close * adjustment_factor / terminal_adjustment_factor AS forward_adjusted_close,
  raw_open * adjustment_factor AS backward_adjusted_open,
  raw_high * adjustment_factor AS backward_adjusted_high,
  raw_low * adjustment_factor AS backward_adjusted_low,
  raw_close * adjustment_factor AS backward_adjusted_close,
  research_close_index * raw_open / raw_close AS research_open_index,
  research_close_index * raw_high / raw_close AS research_high_index,
  research_close_index * raw_low / raw_close AS research_low_index,
  research_close_index,
  reported_total_return, factor_implied_return,
  abs(factor_implied_return - reported_total_return) * 10000
    AS factor_return_error_bps,
  factor_changed, has_implemented_action_evidence
FROM derived ORDER BY trade_date, instrument_id
) TO '{target}' (FORMAT PARQUET, COMPRESSION ZSTD)
"""


_STATS_SQL = """
SELECT count(*), count(DISTINCT (instrument_id, trade_date)),
       coalesce(count_if(factor_changed), 0),
       coalesce(count_if(factor_changed AND has_implemented_action_evidence), 0),
       coalesce(count_if(factor_return_error_bps > 1), 0),
       coalesce(count_if(
         research_close_index <= 0 OR research_low_index <= 0
         OR research_high_index < research_low_index
       ), 0)
FROM read_parquet(?)
"""


_NEXT_ANCHOR_SQL = """
COPY (
  WITH current_anchor AS (
    SELECT instrument_id, research_close_index, raw_close AS last_raw_close,
           adjustment_factor AS last_adjustment_factor,
           trade_date AS last_trade_date
    FROM read_parquet(?)
    QUALIFY row_number() OVER (
      PARTITION BY instrument_id ORDER BY trade_date DESC
    ) = 1
  )
  SELECT * FROM current_anchor
  UNION ALL
  SELECT p.* FROM prior_index_anchor p
  WHERE NOT EXISTS (
    SELECT 1 FROM current_anchor c WHERE c.instrument_id = p.instrument_id
  )
  ORDER BY instrument_id
) TO '{target}' (FORMAT PARQUET, COMPRESSION ZSTD)
"""


def _index_anchor_view(
    connection: duckdb.DuckDBPyConnection,
    path: Path | None,
) -> None:
    if path is None:
        connection.execute(
            """
            CREATE VIEW prior_index_anchor AS
            SELECT NULL::VARCHAR instrument_id, NULL::DOUBLE research_close_index,
                   NULL::DOUBLE last_raw_close,
                   NULL::DOUBLE last_adjustment_factor,
                   NULL::DATE last_trade_date
            WHERE false
            """
        )
        return
    connection.execute(
        f"CREATE VIEW prior_index_anchor AS SELECT * FROM read_parquet('{_literal(path)}')"
    )


def _literal(path: Path) -> str:
    return str(path).replace("'", "''")


__all__ = ["DuckDBCorporateActionProjector"]
