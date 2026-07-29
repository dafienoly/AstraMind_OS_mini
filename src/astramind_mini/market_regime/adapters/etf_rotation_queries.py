"""Point-in-time DuckDB queries used by the ETF rotation projection."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

import duckdb

from ..contracts.hierarchy import PriceCandle


def load_prices(
    connection: duckdb.DuckDBPyConnection,
    paths: tuple[Path, ...],
    cutoff: date,
) -> tuple[dict[str, list[PriceCandle]], date | None, date | None]:
    rows = connection.execute(
        """
        WITH bounded AS (
          SELECT *, row_number() OVER (
            PARTITION BY instrument_id ORDER BY trade_date DESC
          ) recent_rank
          FROM read_parquet(?) WHERE trade_date <= ? AND available_at::DATE <= ?
        )
        SELECT instrument_id, trade_date, open, high, low, close, volume_lots, amount_cny
        FROM bounded WHERE recent_rank <= 520 ORDER BY instrument_id, trade_date
        """,
        [_strings(paths), cutoff, cutoff],
    ).fetchall()
    grouped: dict[str, list[PriceCandle]] = defaultdict(list)
    dates = []
    for row in rows:
        dates.append(row[1])
        grouped[str(row[0])].append(
            PriceCandle(
                trade_date=row[1],
                open=float(row[2]),
                high=float(row[3]),
                low=float(row[4]),
                close=float(row[5]),
                volume_lots=float(row[6]),
                amount_cny=float(row[7]),
            )
        )
    return grouped, min(dates, default=None), max(dates, default=None)


def load_industry_closes(
    connection: duckdb.DuckDBPyConnection,
    paths: tuple[Path, ...],
    cutoff: date,
) -> dict[str, list[tuple[date, float]]]:
    rows = connection.execute(
        """
        WITH bounded AS (
          SELECT *, row_number() OVER (
            PARTITION BY industry_code ORDER BY trade_date DESC
          ) recent_rank
          FROM read_parquet(?) WHERE level='L1' AND trade_date <= ?
        )
        SELECT industry_code, trade_date, close FROM bounded
        WHERE recent_rank <= 520 ORDER BY industry_code, trade_date
        """,
        [_strings(paths), cutoff],
    ).fetchall()
    grouped: dict[str, list[tuple[date, float]]] = defaultdict(list)
    for row in rows:
        grouped[str(row[0])].append((row[1], float(row[2])))
    return grouped


def expected_cutoff(
    connection: duckdb.DuckDBPyConnection,
    paths: tuple[Path, ...],
    as_of: datetime,
) -> date:
    local = as_of.astimezone(ZoneInfo("Asia/Shanghai"))
    upper = local.date()
    if local.time() < time(18):
        upper = date.fromordinal(upper.toordinal() - 1)
    row = connection.execute(
        """
        SELECT max(calendar_date) FROM read_parquet(?)
        WHERE exchange='SSE' AND is_open AND calendar_date <= ?
        """,
        [_strings(paths), upper],
    ).fetchone()
    if row is None or not isinstance(row[0], date):
        raise ValueError("ETF 轮动无法解析完成交易日")
    return row[0]


def parquet_paths(paths: tuple[Path, ...]) -> list[str]:
    return _strings(paths)


def _strings(paths: tuple[Path, ...]) -> list[str]:
    return [str(item) for item in paths]


__all__ = [
    "expected_cutoff",
    "load_industry_closes",
    "load_prices",
    "parquet_paths",
]
