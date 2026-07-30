"""DuckDB query primitives for one frozen daily price-history window."""

from __future__ import annotations

from calendar import monthrange
from dataclasses import dataclass
from datetime import date
from typing import Any

import duckdb

from ..contracts.hierarchy import PriceCandle
from ..contracts.price_history import HistoryWindow, InstrumentType


@dataclass(frozen=True, slots=True)
class HistoryIdentity:
    name: str
    listing_date: date | None


@dataclass(frozen=True, slots=True)
class HistoryQuery:
    identity: HistoryIdentity
    coverage_start: date | None
    coverage_end: date | None
    requested_start: date
    requested_end: date
    rows: tuple[tuple[Any, ...], ...]


def query_history(
    paths: dict[str, list[str]],
    *,
    instrument_type: InstrumentType,
    instrument_id: str,
    dataset_name: str,
    window: HistoryWindow,
    cutoff: date,
    requested_end: date,
    start: date | None,
    cursor: date | None,
    page_size: int,
) -> HistoryQuery:
    with duckdb.connect(":memory:") as connection:
        identity = _identity(
            connection,
            paths,
            instrument_type=instrument_type,
            instrument_id=instrument_id,
            cutoff=cutoff,
        )
        coverage_start, coverage_end = _coverage(
            connection,
            paths[dataset_name],
            instrument_type=instrument_type,
            instrument_id=instrument_id,
            cutoff=cutoff,
        )
        requested_start = start or _window_start(
            window,
            requested_end,
            identity.listing_date,
            coverage_start,
        )
        _validate_window(requested_start, requested_end, cursor)
        rows = tuple(
            _bars(
                connection,
                paths[dataset_name],
                instrument_type=instrument_type,
                instrument_id=instrument_id,
                start=requested_start,
                end=requested_end,
                availability_cutoff=cutoff,
                cursor=cursor,
                page_size=page_size,
            )
        )
    return HistoryQuery(
        identity=identity,
        coverage_start=coverage_start,
        coverage_end=coverage_end,
        requested_start=requested_start,
        requested_end=requested_end,
        rows=rows,
    )


def price_candle(instrument_type: InstrumentType, row: tuple[Any, ...]) -> PriceCandle:
    return PriceCandle(
        trade_date=row[0],
        open=float(row[1]),
        high=float(row[2]),
        low=float(row[3]),
        close=float(row[4]),
        volume_lots=float(row[5]),
        amount_cny=float(row[6]) if row[6] is not None else None,
    )


def _validate_window(start: date, end: date, cursor: date | None) -> None:
    if start > end:
        raise ValueError("历史行情开始日期不能晚于结束日期")
    if cursor is not None and not start < cursor <= end:
        raise ValueError("历史行情游标不在冻结日期窗口内")


def _identity(
    connection: duckdb.DuckDBPyConnection,
    paths: dict[str, list[str]],
    *,
    instrument_type: InstrumentType,
    instrument_id: str,
    cutoff: date,
) -> HistoryIdentity:
    if instrument_type == "stock":
        row = connection.execute(
            """
            SELECT name, list_date FROM read_parquet(?)
            WHERE instrument_id = ? AND CAST(available_at AS DATE) <= ?
            LIMIT 1
            """,
            [paths["security_master"], instrument_id, cutoff],
        ).fetchone()
    elif instrument_type == "etf":
        row = connection.execute(
            """
            SELECT name, list_date FROM read_parquet(?)
            WHERE instrument_id = ? AND CAST(available_at AS DATE) <= ?
            LIMIT 1
            """,
            [paths["etf_master"], instrument_id, cutoff],
        ).fetchone()
    else:
        row = connection.execute(
            """
            SELECT arg_max(instrument_name, trade_date), NULL::DATE
            FROM read_parquet(?) WHERE instrument_id = ? AND trade_date <= ?
            """,
            [paths["broad_index_daily"], instrument_id, cutoff],
        ).fetchone()
    if row is None or row[0] is None:
        raise FileNotFoundError(instrument_id)
    return HistoryIdentity(str(row[0]), row[1] if isinstance(row[1], date) else None)


def _coverage(
    connection: duckdb.DuckDBPyConnection,
    paths: list[str],
    *,
    instrument_type: InstrumentType,
    instrument_id: str,
    cutoff: date,
) -> tuple[date | None, date | None]:
    available = "AND CAST(available_at AS DATE) <= ?" if instrument_type != "index" else ""
    params: list[object] = [paths, instrument_id, cutoff]
    if available:
        params.append(cutoff)
    row = connection.execute(
        f"""
        SELECT min(trade_date), max(trade_date) FROM read_parquet(?)
        WHERE instrument_id = ? AND trade_date <= ? {available}
        """,
        params,
    ).fetchone()
    if row is None:
        return None, None
    return (
        row[0] if isinstance(row[0], date) else None,
        row[1] if isinstance(row[1], date) else None,
    )


def _bars(
    connection: duckdb.DuckDBPyConnection,
    paths: list[str],
    *,
    instrument_type: InstrumentType,
    instrument_id: str,
    start: date,
    end: date,
    availability_cutoff: date,
    cursor: date | None,
    page_size: int,
) -> list[tuple[Any, ...]]:
    amount = "amount_thousand_cny * 1000" if instrument_type == "stock" else "amount_cny"
    available = "AND CAST(available_at AS DATE) <= ?" if instrument_type != "index" else ""
    cursor_clause = "AND trade_date < ?" if cursor is not None else ""
    params: list[object] = [paths, instrument_id, start, end]
    if cursor is not None:
        params.append(cursor)
    if available:
        params.append(availability_cutoff)
    params.append(page_size + 1)
    return connection.execute(
        f"""
        SELECT trade_date, open, high, low, close, volume_lots, {amount}
        FROM read_parquet(?)
        WHERE instrument_id = ? AND trade_date BETWEEN ? AND ?
          {cursor_clause} {available}
        ORDER BY trade_date DESC LIMIT ?
        """,
        params,
    ).fetchall()


def _window_start(
    window: HistoryWindow,
    end: date,
    listing_date: date | None,
    coverage_start: date | None,
) -> date:
    if window == "one_year":
        return _subtract_years(end, 1)
    if window == "five_years":
        return _subtract_years(end, 5)
    if listing_date is not None:
        return listing_date
    return coverage_start or end


def _subtract_years(value: date, years: int) -> date:
    year = value.year - years
    return date(year, value.month, min(value.day, monthrange(year, value.month)[1]))


__all__ = ["HistoryQuery", "price_candle", "query_history"]
