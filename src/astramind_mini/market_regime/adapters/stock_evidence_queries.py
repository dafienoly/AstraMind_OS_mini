"""Point-in-time stock price and evidence queries for the hierarchy workbench."""

from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime
from decimal import Decimal
from itertools import pairwise
from typing import Literal
from zoneinfo import ZoneInfo

import duckdb

from ..contracts.hierarchy import (
    PriceCandle,
    ShareholderConcentrationEvidence,
    StockEvidence,
    StockFundamentalEvidence,
)

Period = Literal["day", "week", "month"]


def price_candles(
    connection: duckdb.DuckDBPyConnection,
    market_paths: list[str],
    calendar_paths: list[str],
    *,
    instrument_id: str | None,
    as_of: date,
    period: Period,
) -> tuple[PriceCandle, ...]:
    if instrument_id is None:
        return ()
    history_start = _one_year_before(as_of)
    if period == "day":
        rows = connection.execute(
            """
            SELECT trade_date, open, high, low, close, volume_lots,
                   amount_thousand_cny * 1000
            FROM read_parquet(?)
            WHERE instrument_id = ? AND trade_date BETWEEN ? AND ?
            ORDER BY trade_date DESC
            """,
            [market_paths, instrument_id, history_start, as_of],
        ).fetchall()
    else:
        rows = _aggregate_period(
            connection,
            market_paths,
            calendar_paths,
            instrument_id=instrument_id,
            start=history_start,
            as_of=as_of,
            period=period,
        )
    return tuple(
        PriceCandle(
            trade_date=day,
            open=float(open_),
            high=float(high),
            low=float(low),
            close=float(close),
            volume_lots=float(volume),
            amount_cny=float(amount) if amount is not None else None,
        )
        for day, open_, high, low, close, volume, amount in reversed(rows)
    )


def _aggregate_period(
    connection: duckdb.DuckDBPyConnection,
    market_paths: list[str],
    calendar_paths: list[str],
    *,
    instrument_id: str,
    start: date,
    as_of: date,
    period: Literal["week", "month"],
) -> list[tuple[object, ...]]:
    bucket = "week" if period == "week" else "month"
    return connection.execute(
        f"""
        WITH calendar_ends AS (
          SELECT CAST(date_trunc('{bucket}', calendar_date) AS DATE) AS bucket,
                 max(calendar_date) AS period_end
          FROM read_parquet(?)
          WHERE exchange = 'SSE' AND is_open
          GROUP BY bucket
        ), bars AS (
          SELECT CAST(date_trunc('{bucket}', trade_date) AS DATE) AS bucket,
                 arg_min(open, trade_date) AS open,
                 max(high) AS high,
                 min(low) AS low,
                 arg_max(close, trade_date) AS close,
                 sum(volume_lots) AS volume_lots,
                 sum(amount_thousand_cny) * 1000 AS amount_cny
          FROM read_parquet(?)
          WHERE instrument_id = ? AND trade_date BETWEEN ? AND ?
          GROUP BY bucket
        )
        SELECT c.period_end, b.open, b.high, b.low, b.close, b.volume_lots, b.amount_cny
        FROM bars b JOIN calendar_ends c USING (bucket)
        WHERE c.period_end <= ?
        ORDER BY c.period_end DESC
        """,
        [calendar_paths, market_paths, instrument_id, start, as_of, as_of],
    ).fetchall()


def stock_evidence(
    connection: duckdb.DuckDBPyConnection,
    paths: dict[str, list[str]],
    *,
    instrument_id: str,
    instrument_name: str,
    as_of: date,
) -> StockEvidence:
    fundamental_history = _fundamental_history(
        connection,
        paths.get("daily_market", []),
        paths.get("daily_basic", []),
        instrument_id=instrument_id,
        as_of=as_of,
    )
    fundamental = fundamental_history[-1] if fundamental_history else None
    shareholder, shareholder_history = _shareholder_evidence(
        connection,
        paths.get("shareholder_count", []),
        instrument_id=instrument_id,
        as_of=as_of,
    )
    gaps: list[str] = []
    if fundamental is None:
        gaps.append("stock_fundamental_unavailable")
    gaps.extend(shareholder.known_gaps)
    return StockEvidence(
        instrument_id=instrument_id,
        instrument_name=instrument_name,
        as_of=as_of,
        fundamental=fundamental,
        fundamental_history=fundamental_history,
        shareholder_concentration=shareholder,
        shareholder_concentration_history=shareholder_history,
        known_gaps=tuple(gaps),
    )


def _fundamental_history(
    connection: duckdb.DuckDBPyConnection,
    market_paths: list[str],
    basic_paths: list[str],
    *,
    instrument_id: str,
    as_of: date,
) -> tuple[StockFundamentalEvidence, ...]:
    if not market_paths or not basic_paths:
        return ()
    rows = connection.execute(
        """
        WITH evidence AS (
          SELECT m.trade_date, greatest(m.available_at, b.available_at) available_at,
                 m.close, m.percent_change, b.turnover_rate, b.price_earnings_ttm,
                 b.price_book, b.total_market_value_ten_thousand_cny * 10000 total_mv,
                 b.circulating_market_value_ten_thousand_cny * 10000 circulating_mv,
                 m.amount_thousand_cny * 1000 amount_cny
          FROM read_parquet(?) m
          LEFT JOIN read_parquet(?) b USING (instrument_id, trade_date)
          WHERE m.instrument_id = ?
            AND m.trade_date BETWEEN (? - INTERVAL 5 YEAR) AND ?
            AND CAST(m.available_at AT TIME ZONE 'Asia/Shanghai' AS DATE) <= ?
            AND (
              b.available_at IS NULL
              OR CAST(b.available_at AT TIME ZONE 'Asia/Shanghai' AS DATE) <= ?
            )
        )
        SELECT trade_date, available_at, close, percent_change, turnover_rate,
               price_earnings_ttm, price_book, total_mv, circulating_mv, amount_cny
        FROM evidence
        ORDER BY trade_date
        """,
        [market_paths, basic_paths, instrument_id, as_of, as_of, as_of, as_of],
    ).fetchall()
    return tuple(
        StockFundamentalEvidence(
            market_date=row[0],
            available_at=_aware(row[1]),
            latest_close=float(row[2]),
            percent_change=_float(row[3]),
            turnover_rate=_float(row[4]),
            price_earnings_ttm=_float(row[5]),
            price_book=_float(row[6]),
            total_market_value_cny=_float(row[7]),
            circulating_market_value_cny=_float(row[8]),
            amount_cny=_float(row[9]),
        )
        for row in rows
    )


def _shareholder_evidence(
    connection: duckdb.DuckDBPyConnection,
    holder_paths: list[str],
    *,
    instrument_id: str,
    as_of: date,
) -> tuple[
    ShareholderConcentrationEvidence,
    tuple[ShareholderConcentrationEvidence, ...],
]:
    if not holder_paths:
        unavailable = ShareholderConcentrationEvidence(
            status="unavailable",
            known_gaps=("shareholder_count_not_in_snapshot",),
        )
        return unavailable, ()
    rows = connection.execute(
        """
        SELECT announced_on, reporting_period, available_at, holder_count
        FROM read_parquet(?)
        WHERE instrument_id = ? AND holder_count IS NOT NULL
          AND CAST(available_at AT TIME ZONE 'Asia/Shanghai' AS DATE) <= ?
        ORDER BY available_at DESC, reporting_period DESC LIMIT 64
        """,
        [holder_paths, instrument_id, as_of],
    ).fetchall()
    if not rows:
        unavailable = ShareholderConcentrationEvidence(
            status="unavailable",
            known_gaps=("shareholder_count_instrument_unavailable",),
        )
        return unavailable, ()
    current = _shareholder_from_rows(rows, as_of)
    history = tuple(
        _shareholder_from_rows(rows[index:], _available_date(rows[index][2]))
        for index in reversed(range(len(rows)))
    )
    return current, history


def _shareholder_from_rows(
    rows: list[tuple[object, ...]],
    as_of: date,
) -> ShareholderConcentrationEvidence:
    latest = rows[0]
    announced_on = _date(latest[0])
    reporting_period = _date(latest[1])
    if len(rows) < 2:
        return ShareholderConcentrationEvidence(
            status="insufficient_history",
            announced_on=announced_on,
            reporting_period=reporting_period,
            available_at=_aware(latest[2]),
            holder_count=_integer(latest[3]),
            observation_age_days=(as_of - announced_on).days,
            known_gaps=("shareholder_count_previous_period_unavailable",),
        )
    counts = [_integer(row[3]) for row in rows]
    change = counts[0] / counts[1] - 1
    direction: Literal["concentrating", "dispersing", "unchanged"]
    direction = "concentrating" if change < 0 else "dispersing" if change > 0 else "unchanged"
    consecutive = _consecutive_direction(counts, direction)
    return ShareholderConcentrationEvidence(
        status="ready",
        announced_on=announced_on,
        reporting_period=reporting_period,
        available_at=_aware(latest[2]),
        holder_count=counts[0],
        previous_holder_count=counts[1],
        change_rate=change,
        direction=direction,
        consecutive_periods=consecutive,
        observation_age_days=(as_of - announced_on).days,
    )


def _consecutive_direction(
    counts: list[int],
    direction: Literal["concentrating", "dispersing", "unchanged"],
) -> int:
    expected = -1 if direction == "concentrating" else 1 if direction == "dispersing" else 0
    result = 0
    for current, previous in pairwise(counts):
        observed = -1 if current < previous else 1 if current > previous else 0
        if observed != expected:
            break
        result += 1
    return result


def _aware(value: object) -> datetime:
    if not isinstance(value, datetime):
        raise ValueError("证据可用时间不是 datetime")
    return value


def _available_date(value: object) -> date:
    return _aware(value).astimezone(ZoneInfo("Asia/Shanghai")).date()


def _date(value: object) -> date:
    if isinstance(value, datetime):
        return value.date()
    if not isinstance(value, date):
        raise ValueError("证据日期不是 date")
    return value


def _integer(value: object) -> int:
    if not isinstance(value, int):
        raise ValueError("股东户数不是 int")
    return value


def _float(value: object) -> float | None:
    if value is None:
        return None
    if not isinstance(value, (int, float, Decimal)):
        raise ValueError("股票证据数值字段类型无效")
    return float(value)


def _one_year_before(value: date) -> date:
    year = value.year - 1
    return date(year, value.month, min(value.day, monthrange(year, value.month)[1]))


__all__ = ["price_candles", "stock_evidence"]
