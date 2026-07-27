"""Annual normalization for legacy valuation and trading-constraint tables."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import duckdb

SUPPORTED_TABLES = {"daily_basic", "stk_limit", "suspend_d"}


class LegacyConstraintAnnualCompactor:
    def compact(
        self,
        *,
        table: str,
        source_files: tuple[Path, ...],
        supplement_files: tuple[Path, ...],
        output: Path,
        imported_at: datetime,
    ) -> tuple[int, int]:
        if table not in SUPPORTED_TABLES:
            raise ValueError(f"不支持旧约束表：{table}")
        if not source_files and not supplement_files:
            raise ValueError("年度分区没有输入文件")
        output.parent.mkdir(parents=True, exist_ok=True)
        temporary = output.with_suffix(output.suffix + ".tmp")
        temporary.unlink(missing_ok=True)
        parts: list[str] = []
        parameters: list[object] = []
        if source_files:
            parts.append(_legacy_projection(table))
            parameters.extend((imported_at, [str(path) for path in source_files]))
        if supplement_files:
            parts.append("SELECT * FROM read_parquet(?)")
            parameters.append([str(path) for path in supplement_files])
        union = " UNION ALL ".join(parts)
        order = _order_by(table)
        primary_key = _primary_key(table)
        output_literal = str(temporary).replace("'", "''")
        with duckdb.connect(":memory:") as connection:
            connection.execute(
                f"COPY (SELECT * FROM ({union}) ORDER BY {order}) "
                f"TO '{output_literal}' (FORMAT PARQUET, COMPRESSION ZSTD)",
                parameters,
            )
            counts = connection.execute(
                f"SELECT count(*), count(DISTINCT ({primary_key})) FROM read_parquet(?)",
                [str(temporary)],
            ).fetchone()
        assert counts is not None
        row_count, distinct_count = map(int, counts)
        if row_count != distinct_count:
            temporary.unlink(missing_ok=True)
            raise ValueError(f"{table} 年度分区存在重复主键")
        temporary.replace(output)
        return row_count, distinct_count

    def validate(self, table: str, path: Path) -> dict[str, int]:
        if table not in SUPPORTED_TABLES:
            raise ValueError(f"不支持旧约束表：{table}")
        with duckdb.connect(":memory:") as connection:
            if table == "daily_basic":
                row = connection.execute(
                    """
                    SELECT count_if(
                        close <= 0 OR turnover_rate < 0
                        OR turnover_rate_free_float < 0
                        OR total_shares_ten_thousand < 0
                        OR float_shares_ten_thousand < 0
                        OR free_float_shares_ten_thousand < 0
                        OR total_market_value_ten_thousand_cny < 0
                        OR circulating_market_value_ten_thousand_cny < 0
                    )
                    FROM read_parquet(?)
                    """,
                    [str(path)],
                ).fetchone()
                assert row is not None
                if row[0]:
                    raise ValueError("daily_basic 包含无效价格、换手、股本或市值")
                return {"invalid_rows": 0}
            if table == "stk_limit":
                row = connection.execute(
                    "SELECT count_if(NOT limit_prices_usable) FROM read_parquet(?)",
                    [str(path)],
                ).fetchone()
                assert row is not None
                return {"unusable_limit_rows": int(row[0])}
            row = connection.execute(
                """
                SELECT count_if(suspension_type NOT IN ('S', 'R')),
                       count_if(suspension_timing IS NOT NULL)
                FROM read_parquet(?)
                """,
                [str(path)],
            ).fetchone()
            assert row is not None
            if row[0]:
                raise ValueError("suspend_d 包含未知事件类型")
            return {"timed_event_rows": int(row[1])}


def _legacy_projection(table: str) -> str:
    available_offset = "8 hours 40 minutes" if table == "stk_limit" else "18 hours"
    common = f"""
        'tushare' AS provider,
        'legacy-astramind-silver' AS source_endpoint,
        CAST(? AS TIMESTAMPTZ) AS retrieved_at,
        timezone(
            'Asia/Shanghai',
            CAST(trade_date AS TIMESTAMP) + INTERVAL '{available_offset}'
        ) AS available_at,
        '1.0.0' AS schema_version
    """
    if table == "daily_basic":
        identity = "ts_code || '|' || CAST(trade_date AS VARCHAR)"
        fields = """
            ts_code AS instrument_id,
            trade_date,
            close,
            turnover_rate,
            turnover_rate_f AS turnover_rate_free_float,
            volume_ratio,
            pe AS price_earnings,
            pe_ttm AS price_earnings_ttm,
            pb AS price_book,
            ps AS price_sales,
            ps_ttm AS price_sales_ttm,
            dv_ratio AS dividend_yield,
            dv_ttm AS dividend_yield_ttm,
            total_share AS total_shares_ten_thousand,
            float_share AS float_shares_ten_thousand,
            free_share AS free_float_shares_ten_thousand,
            total_mv AS total_market_value_ten_thousand_cny,
            circ_mv AS circulating_market_value_ten_thousand_cny
        """
    elif table == "stk_limit":
        identity = "ts_code || '|' || CAST(trade_date AS VARCHAR)"
        fields = """
            ts_code AS instrument_id,
            trade_date,
            pre_close AS previous_close,
            up_limit AS upper_limit,
            down_limit AS lower_limit,
            coalesce(up_limit > 0 AND down_limit > 0 AND up_limit >= down_limit, false)
                AS limit_prices_usable
        """
    else:
        identity = """
            ts_code || '|' || CAST(trade_date AS VARCHAR) || '|' ||
            suspend_type || '|' || coalesce(suspend_timing, '')
        """
        fields = """
            ts_code AS instrument_id,
            trade_date,
            suspend_timing AS suspension_timing,
            suspend_type AS suspension_type
        """
    source_hash = f"""
        'sha256:' || sha256(coalesce(_raw_sha256, '') || '|' || {identity})
            AS source_record_hash
    """
    return f"SELECT {common}, {source_hash}, {fields} FROM read_parquet(?)"


def _order_by(table: str) -> str:
    if table == "suspend_d":
        return "trade_date, instrument_id, suspension_type, suspension_timing"
    return "trade_date, instrument_id"


def _primary_key(table: str) -> str:
    if table == "suspend_d":
        return "instrument_id, trade_date, suspension_type, suspension_timing"
    return "instrument_id, trade_date"


__all__ = ["LegacyConstraintAnnualCompactor"]
