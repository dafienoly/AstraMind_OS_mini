"""Bounded publication policy for the first production market snapshot."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from ..contracts import SecurityMasterObservation, TradeCalendarObservation

SHANGHAI = ZoneInfo("Asia/Shanghai")
PROVIDER_LIMIT = 6000

SECURITY_FIELDS = (
    "ts_code",
    "symbol",
    "name",
    "area",
    "industry",
    "market",
    "exchange",
    "curr_type",
    "list_status",
    "list_date",
    "delist_date",
    "is_hs",
)
CALENDAR_FIELDS = ("exchange", "cal_date", "is_open", "pretrade_date")
DAILY_FIELDS = (
    "ts_code",
    "trade_date",
    "open",
    "high",
    "low",
    "close",
    "pre_close",
    "change",
    "pct_chg",
    "vol",
    "amount",
)
ADJUSTMENT_FIELDS = ("ts_code", "trade_date", "adj_factor")
DAILY_BASIC_FIELDS = (
    "ts_code",
    "trade_date",
    "close",
    "turnover_rate",
    "turnover_rate_f",
    "volume_ratio",
    "pe",
    "pe_ttm",
    "pb",
    "ps",
    "ps_ttm",
    "dv_ratio",
    "dv_ttm",
    "total_share",
    "float_share",
    "free_share",
    "total_mv",
    "circ_mv",
)
PRICE_LIMIT_FIELDS = ("trade_date", "ts_code", "pre_close", "up_limit", "down_limit")
SUSPENSION_FIELDS = ("ts_code", "trade_date", "suspend_timing", "suspend_type")
PRIMARY_KEYS = {
    "security_master": ("instrument_id",),
    "trade_calendar": ("exchange", "calendar_date"),
    "daily_market": ("instrument_id", "trade_date"),
    "adjustment_factor": ("instrument_id", "trade_date"),
    "daily_basic": ("instrument_id", "trade_date"),
    "price_limit": ("instrument_id", "trade_date"),
    "suspension_event": (
        "instrument_id",
        "trade_date",
        "suspension_type",
        "suspension_timing",
    ),
}
UNITS = {
    "security_master": (),
    "trade_calendar": (),
    "daily_market": ("price:CNY", "volume:lot", "amount:thousand_CNY"),
    "adjustment_factor": ("adjustment_factor:ratio",),
    "daily_basic": (
        "turnover_rate:percent",
        "shares:ten_thousand_shares",
        "market_value:ten_thousand_CNY",
    ),
    "price_limit": ("price:CNY",),
    "suspension_event": (),
}


def completed_session_cutoff(value: datetime) -> date:
    local = value.astimezone(SHANGHAI)
    if local.timetz().replace(tzinfo=None) < time(18, 0):
        return local.date() - timedelta(days=1)
    return local.date()


def date_chunks(start: date, end: date) -> tuple[tuple[date, date], ...]:
    chunks = []
    current = start
    while current <= end:
        chunk_end = min(date(current.year + 9, 12, 31), end)
        chunks.append((current, chunk_end))
        current = chunk_end + timedelta(days=1)
    return tuple(chunks)


def latest_common_open_date(
    rows: Sequence[TradeCalendarObservation],
    cutoff: date,
) -> date:
    by_exchange: dict[str, set[date]] = {"SSE": set(), "SZSE": set()}
    for item in rows:
        if item.is_open and item.calendar_date <= cutoff:
            by_exchange.setdefault(item.exchange, set()).add(item.calendar_date)
    common = by_exchange["SSE"] & by_exchange["SZSE"]
    if not common:
        raise ValueError("SSE/SZSE 没有共同的已完成交易日")
    return max(common)


def active_security_count(
    rows: Sequence[SecurityMasterObservation],
    as_of: date,
) -> int:
    return sum(
        1
        for row in rows
        if row.list_date is not None
        and row.list_date <= as_of
        and (row.delist_date is None or row.delist_date > as_of)
    )


__all__ = [
    "ADJUSTMENT_FIELDS",
    "CALENDAR_FIELDS",
    "DAILY_BASIC_FIELDS",
    "DAILY_FIELDS",
    "PRICE_LIMIT_FIELDS",
    "PRIMARY_KEYS",
    "PROVIDER_LIMIT",
    "SECURITY_FIELDS",
    "SUSPENSION_FIELDS",
    "UNITS",
    "active_security_count",
    "completed_session_cutoff",
    "date_chunks",
    "latest_common_open_date",
]
