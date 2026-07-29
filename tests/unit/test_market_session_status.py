from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from astramind_mini.data.application.identity import content_hash
from astramind_mini.data.application.market_session_status import (
    SHANGHAI,
    MarketSessionContext,
    assess_market_session,
)
from astramind_mini.data.contracts.realtime_projection import RealtimeMarketProjection

OPEN_DATES = tuple(date(2026, 7, day) for day in range(27, 32))


def local_time(day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 7, day, hour, minute, tzinfo=SHANGHAI).astimezone(UTC)


@pytest.mark.parametrize(
    ("now", "completed", "expected"),
    [
        (local_time(30, 9), date(2026, 7, 29), "pre_open"),
        (local_time(30, 12), date(2026, 7, 29), "lunch_break"),
        (local_time(30, 15, 30), date(2026, 7, 30), "closed"),
        (local_time(31, 15, 30) + timedelta(days=1), date(2026, 7, 31), "non_trading_day"),
    ],
)
def test_non_streaming_market_phases_ignore_old_tick_age(
    now: datetime,
    completed: date,
    expected: str,
) -> None:
    status = assess_market_session(
        now=now,
        latest_received_at=now - timedelta(hours=1),
        transport_disconnected=False,
        context=MarketSessionContext(
            open_dates=OPEN_DATES,
            latest_completed_trade_date=completed,
        ),
    )

    assert status.operational_state == expected
    assert status.daily_data_state == "current"


def test_continuous_auction_uses_tick_age_and_recovers() -> None:
    now = local_time(30, 10)
    context = MarketSessionContext(
        open_dates=OPEN_DATES,
        latest_completed_trade_date=date(2026, 7, 29),
    )

    delayed = assess_market_session(
        now=now,
        latest_received_at=now - timedelta(seconds=11),
        transport_disconnected=False,
        context=context,
    )
    recovered = assess_market_session(
        now=now,
        latest_received_at=now - timedelta(seconds=1),
        transport_disconnected=False,
        context=context,
    )

    assert delayed.operational_state == "update_delayed"
    assert delayed.legacy_state == "stale"
    assert recovered.operational_state == "updating"
    assert recovered.legacy_state == "current"


def test_transport_disconnect_and_daily_lag_are_independent() -> None:
    now = local_time(30, 15, 30)
    context = MarketSessionContext(
        open_dates=OPEN_DATES,
        latest_completed_trade_date=date(2026, 7, 29),
    )

    connected = assess_market_session(
        now=now,
        latest_received_at=now - timedelta(hours=1),
        transport_disconnected=False,
        context=context,
    )
    disconnected = assess_market_session(
        now=now,
        latest_received_at=now - timedelta(hours=1),
        transport_disconnected=True,
        context=context,
    )

    assert connected.operational_state == "daily_lagging"
    assert connected.transport_health == "connected"
    assert disconnected.operational_state == "disconnected"
    assert disconnected.daily_data_state == "lagging"


def test_missing_calendar_is_unknown_instead_of_healthy() -> None:
    now = local_time(30, 10)

    status = assess_market_session(
        now=now,
        latest_received_at=now,
        transport_disconnected=False,
        context=None,
    )

    assert status.market_session == "unknown"
    assert status.daily_data_state == "unknown"
    assert status.operational_state == "unknown"
    assert status.legacy_state == "stale"


def test_naive_clock_is_rejected() -> None:
    with pytest.raises(ValueError, match="必须带时区"):
        assess_market_session(
            now=datetime(2026, 7, 30, 10),
            latest_received_at=None,
            transport_disconnected=False,
            context=None,
        )


def test_realtime_contract_accepts_pre_wp0058_payload() -> None:
    now = local_time(30, 10)
    projection = RealtimeMarketProjection.model_validate(
        {
            "projection_id": content_hash({"projection": "legacy"}),
            "provider": "miniqmt",
            "session_id": content_hash({"session": "legacy"}),
            "state": "current",
            "as_of": now,
            "latest_received_at": now,
            "granularity_ms": 1000,
            "quote_count": 0,
            "advancing": 0,
            "declining": 0,
            "unchanged": 0,
            "total_amount": 0,
        }
    )

    assert projection.state == "current"
    assert projection.market_session == "unknown"
    assert projection.daily_data_state == "unknown"
    assert projection.operational_state == "unknown"
