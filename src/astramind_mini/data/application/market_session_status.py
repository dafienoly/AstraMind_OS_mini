"""Pure A-share market-session, transport, and daily-completion semantics."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from ..contracts.realtime_projection import (
    DailyDataState,
    MarketSessionPhase,
    RealtimeMarketProjection,
    RealtimeOperationalState,
    TransportHealth,
)

SHANGHAI = ZoneInfo("Asia/Shanghai")
FRESHNESS_THRESHOLD = timedelta(seconds=10)


@dataclass(frozen=True, slots=True)
class MarketSessionContext:
    calendar_dates: tuple[date, ...]
    open_dates: tuple[date, ...]
    latest_completed_trade_date: date | None


@dataclass(frozen=True, slots=True)
class MarketSessionStatus:
    transport_health: TransportHealth
    market_session: MarketSessionPhase
    daily_data_state: DailyDataState
    operational_state: RealtimeOperationalState
    latest_trading_date: date | None
    latest_completed_trade_date: date | None
    legacy_state: Literal["current", "stale", "disconnected"]


def assess_market_session(
    *,
    now: datetime,
    latest_received_at: datetime | None,
    transport_disconnected: bool,
    context: MarketSessionContext | None,
) -> MarketSessionStatus:
    """Assess independent status dimensions at one explicit clock instant."""
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("市场会话状态时钟必须带时区")
    local = now.astimezone(SHANGHAI)
    phase = _phase(local, context)
    latest_trading = _latest_trading_date(local.date(), context)
    expected_completed = _expected_completed_date(local, phase, context)
    completed = context.latest_completed_trade_date if context else None
    daily_state = _daily_state(completed, expected_completed)
    transport: TransportHealth = "disconnected" if transport_disconnected else "connected"
    delayed = latest_received_at is None or now - latest_received_at > FRESHNESS_THRESHOLD
    operational = _operational_state(
        phase=phase,
        transport=transport,
        daily_state=daily_state,
        delayed=delayed,
    )
    return MarketSessionStatus(
        transport_health=transport,
        market_session=phase,
        daily_data_state=daily_state,
        operational_state=operational,
        latest_trading_date=latest_trading,
        latest_completed_trade_date=completed,
        legacy_state=_legacy_state(operational),
    )


def enrich_market_projection(
    projection: RealtimeMarketProjection,
    *,
    now: datetime,
    context: MarketSessionContext | None,
) -> RealtimeMarketProjection:
    status = assess_market_session(
        now=now,
        latest_received_at=projection.latest_received_at,
        transport_disconnected=projection.state == "disconnected",
        context=context,
    )
    return projection.model_copy(
        update={
            "state": status.legacy_state,
            "transport_health": status.transport_health,
            "market_session": status.market_session,
            "daily_data_state": status.daily_data_state,
            "operational_state": status.operational_state,
            "latest_completed_trade_date": status.latest_completed_trade_date,
            "latest_trading_date": status.latest_trading_date,
            "as_of": now,
        }
    )


def _phase(local: datetime, context: MarketSessionContext | None) -> MarketSessionPhase:
    if context is None or local.date() not in context.calendar_dates:
        return "unknown"
    if local.date() not in context.open_dates:
        return "non_trading_day"
    clock = local.time()
    if clock < time(9, 30):
        return "pre_open"
    if time(9, 30) <= clock < time(11, 30) or time(13) <= clock < time(15):
        return "continuous_auction"
    if time(11, 30) <= clock < time(13):
        return "lunch_break"
    return "closed"


def _latest_trading_date(
    today: date,
    context: MarketSessionContext | None,
) -> date | None:
    if context is None or today not in context.calendar_dates:
        return None
    return max((day for day in context.open_dates if day <= today), default=None)


def _expected_completed_date(
    local: datetime,
    phase: MarketSessionPhase,
    context: MarketSessionContext | None,
) -> date | None:
    if context is None or phase == "unknown":
        return None
    if phase in {"closed", "non_trading_day"}:
        upper = local.date()
    else:
        upper = date.fromordinal(local.date().toordinal() - 1)
    return max((day for day in context.open_dates if day <= upper), default=None)


def _daily_state(completed: date | None, expected: date | None) -> DailyDataState:
    if completed is None or expected is None:
        return "unknown"
    return "current" if completed >= expected else "lagging"


def _operational_state(
    *,
    phase: MarketSessionPhase,
    transport: TransportHealth,
    daily_state: DailyDataState,
    delayed: bool,
) -> RealtimeOperationalState:
    if transport == "disconnected":
        return "disconnected"
    if daily_state == "lagging":
        return "daily_lagging"
    if phase == "continuous_auction":
        return "update_delayed" if delayed else "updating"
    if phase in {"pre_open", "lunch_break", "closed", "non_trading_day"}:
        return phase
    return "unknown"


def _legacy_state(
    operational: RealtimeOperationalState,
) -> Literal["current", "stale", "disconnected"]:
    if operational == "disconnected":
        return "disconnected"
    if operational == "updating":
        return "current"
    if operational in {"pre_open", "lunch_break", "closed", "non_trading_day"}:
        return "current"
    if operational == "unknown":
        return "stale"
    return "stale"


__all__ = [
    "FRESHNESS_THRESHOLD",
    "MarketSessionContext",
    "MarketSessionStatus",
    "assess_market_session",
    "enrich_market_projection",
]
