"""DuckDB queries for one exact market-dashboard snapshot."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Any, cast

import duckdb

from ..contracts.dashboard import (
    BroadIndexView,
    MarketBreadth,
    MarketLiquidity,
)
from ..contracts.hierarchy import PriceCandle


def index_views(
    connection: duckdb.DuckDBPyConnection,
    path: tuple[Path, ...],
    cutoff: date,
) -> tuple[BroadIndexView, ...]:
    rows = connection.execute(
        """
        WITH bounded AS (
          SELECT *, row_number() OVER (
            PARTITION BY instrument_id ORDER BY trade_date DESC
          ) AS recent_rank
          FROM read_parquet(?) WHERE trade_date <= ?
        )
        SELECT instrument_id, instrument_name, trade_date, open, high, low, close,
               change, percent_change, volume_lots, amount_cny
        FROM bounded WHERE recent_rank <= 520
        ORDER BY instrument_id, trade_date
        """,
        [[str(item) for item in path], cutoff],
    ).fetchall()
    grouped: dict[str, list[tuple[Any, ...]]] = {}
    for row in rows:
        grouped.setdefault(str(row[0]), []).append(row)
    result = []
    for code, values in grouped.items():
        latest = values[-1]
        close_20_value = float(values[-21][6]) if len(values) > 20 else None
        trailing = values[-250:]
        peak = max(float(row[6]) for row in trailing)
        candles = tuple(
            PriceCandle(
                trade_date=row[2],
                open=float(row[3]),
                high=float(row[4]),
                low=float(row[5]),
                close=float(row[6]),
                volume_lots=float(row[9]),
                amount_cny=float(row[10]) if row[10] is not None else None,
            )
            for row in values
        )
        result.append(
            BroadIndexView(
                instrument_id=code,
                instrument_name=str(latest[1]),
                latest_trade_date=cast(date, latest[2]),
                latest_close=float(latest[6]),
                change=float(latest[7]),
                percent_change=float(latest[8]),
                return_20d=(
                    float(latest[6]) / close_20_value - 1
                    if close_20_value is not None and close_20_value != 0
                    else None
                ),
                drawdown_250d=float(latest[6]) / peak - 1 if peak else None,
                candles=candles,
            )
        )
    return tuple(sorted(result, key=lambda item: _index_order(item.instrument_id)))


def market_totals(
    connection: duckdb.DuckDBPyConnection,
    paths: dict[str, tuple[Path, ...]],
    cutoff: date,
) -> tuple[MarketBreadth, MarketLiquidity]:
    market = [str(item) for item in paths["daily_market"]]
    tradability = [str(item) for item in paths["daily_tradability"]]
    history_start = cutoff - timedelta(days=400)
    row = connection.execute(
        """
        WITH today AS (
          SELECT * FROM read_parquet(?) WHERE trade_date = ?
        ), extrema AS (
          SELECT instrument_id, max(close) AS high_250d, min(close) AS low_250d
          FROM (
            SELECT *, dense_rank() OVER (ORDER BY trade_date DESC) AS session_rank
            FROM read_parquet(?) WHERE trade_date BETWEEN ? AND ?
          ) WHERE session_rank <= 250 GROUP BY instrument_id
        )
        SELECT
          count(*) FILTER (WHERE percent_change > 0),
          count(*) FILTER (WHERE percent_change < 0),
          count(*) FILTER (WHERE percent_change = 0),
          count(*) FILTER (WHERE t.close >= e.high_250d),
          count(*) FILTER (WHERE t.close <= e.low_250d),
          sum(amount_thousand_cny) * 1000
        FROM today t LEFT JOIN extrema e USING (instrument_id)
        """,
        [market, cutoff, market, history_start, cutoff],
    ).fetchone()
    assert row is not None
    locks = connection.execute(
        """
        SELECT count(*) FILTER (WHERE upper_limit_locked),
               count(*) FILTER (WHERE lower_limit_locked)
        FROM read_parquet(?) WHERE trade_date = ?
        """,
        [tradability, cutoff],
    ).fetchone()
    liquidity = connection.execute(
        """
        WITH totals AS (
          SELECT trade_date, sum(amount_thousand_cny) * 1000 AS amount_cny
          FROM read_parquet(?) WHERE trade_date BETWEEN ? AND ?
          GROUP BY trade_date ORDER BY trade_date DESC LIMIT 250
        ), ranked AS (
          SELECT *, row_number() OVER (ORDER BY trade_date DESC) AS rank
          FROM totals
        )
        SELECT max(amount_cny) FILTER (WHERE rank = 1),
               avg(amount_cny) FILTER (WHERE rank BETWEEN 2 AND 21),
               count(*) FILTER (
                 WHERE amount_cny <= (SELECT amount_cny FROM ranked WHERE rank = 1)
               )::DOUBLE / count(*)
        FROM ranked
        """,
        [market, history_start, cutoff],
    ).fetchone()
    assert locks is not None and liquidity is not None
    advancing, declining, unchanged = (int(row[0]), int(row[1]), int(row[2]))
    compared = advancing + declining + unchanged
    amount = float(liquidity[0] or row[5] or 0)
    average = float(liquidity[1]) if liquidity[1] else None
    return (
        MarketBreadth(
            advancing=advancing,
            declining=declining,
            unchanged=unchanged,
            advance_ratio=advancing / compared if compared else 0,
            new_high_250d=int(row[3]),
            new_low_250d=int(row[4]),
            upper_limit_locked=int(locks[0]),
            lower_limit_locked=int(locks[1]),
        ),
        MarketLiquidity(
            amount_cny=amount,
            amount_change_20d=amount / average - 1 if average else None,
            amount_percentile_250d=float(liquidity[2]) if liquidity[2] is not None else None,
        ),
    )


def _index_order(code: str) -> int:
    order = ("000001.SH", "399001.SZ", "399006.SZ", "000688.SH", "000300.SH", "000852.SH")
    return order.index(code) if code in order else len(order)


__all__ = ["index_views", "market_totals"]
