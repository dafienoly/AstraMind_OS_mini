from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from astramind_mini.data.application.identity import content_hash
from astramind_mini.data.application.realtime_minutes import (
    aggregate_session_bars,
    reconcile_minute_parts,
)
from astramind_mini.data.application.realtime_warm_start import (
    normalize_warm_start_minutes,
)
from astramind_mini.data.contracts.realtime_projection import RealtimeMinuteBar
from astramind_mini.data.contracts.source import ProviderBatch

SHANGHAI = ZoneInfo("Asia/Shanghai")


def test_session_aggregation_anchors_am_pm_and_never_crosses_lunch() -> None:
    morning = datetime(2026, 7, 30, 9, 30, tzinfo=SHANGHAI)
    afternoon = datetime(2026, 7, 30, 13, 0, tzinfo=SHANGHAI)
    rows = tuple(
        _bar(morning + timedelta(minutes=index), float(index)) for index in range(120)
    ) + tuple(
        _bar(afternoon + timedelta(minutes=index), float(index + 120)) for index in range(120)
    )

    aggregated = aggregate_session_bars(rows, 120)

    assert [row.minute for row in aggregated] == [morning, afternoon]
    assert aggregated[0].open == 0
    assert aggregated[0].close == 119
    assert aggregated[1].open == 120
    assert aggregated[1].close == 239


def test_incomplete_bucket_and_forming_minute_fail_closed() -> None:
    start = datetime(2026, 7, 30, 9, 30, tzinfo=SHANGHAI)
    rows = tuple(
        _bar(start + timedelta(minutes=index), float(index)) for index in range(15) if index != 7
    )
    forming = _bar(start + timedelta(minutes=7), 7).model_copy(
        update={"is_complete": False, "lifecycle": "forming"}
    )

    assert aggregate_session_bars(rows, 15) == ()
    assert aggregate_session_bars((*rows, forming), 15) == ()


def test_reconnect_parts_are_deterministically_reconciled_and_overlap_is_blocked() -> None:
    minute = datetime(2026, 7, 30, 10, 0, tzinfo=SHANGHAI)
    first = _bar(minute, 10).model_copy(
        update={
            "session_id": content_hash({"session": 1}),
            "first_observed_at": minute,
            "last_observed_at": minute + timedelta(seconds=40),
        }
    )
    second = _bar(minute, 11).model_copy(
        update={
            "session_id": content_hash({"session": 2}),
            "first_observed_at": minute + timedelta(seconds=30),
            "last_observed_at": minute + timedelta(seconds=55),
        }
    )

    reconciled = reconcile_minute_parts((second, first))[0]

    assert reconciled.open == 10
    assert reconciled.close == 11
    assert reconciled.is_complete is False
    assert reconciled.known_gaps == ("overlapping_session_parts",)


def test_warm_start_excludes_current_forming_minute_and_has_content_identity() -> None:
    retrieved = datetime(2026, 7, 30, 10, 1, 20, tzinfo=SHANGHAI)
    request_identity = content_hash({"request": "warm"})
    batch = ProviderBatch(
        provider_id="miniqmt",
        provider_version="test",
        native_interface="get_market_data_ex",
        source_endpoint="local",
        request_identity=request_identity,
        retrieved_at=retrieved,
        rows=(
            _provider_row(datetime(2026, 7, 30, 10, 0, tzinfo=SHANGHAI)),
            _provider_row(datetime(2026, 7, 30, 10, 1, tzinfo=SHANGHAI)),
        ),
        raw_payload={"fixture": True},
        completeness=1,
    )

    rows = normalize_warm_start_minutes(
        batch,
        completed_before=datetime(2026, 7, 30, 10, 1, tzinfo=SHANGHAI),
    )

    assert len(rows) == 1
    assert rows[0].minute.minute == 0
    assert rows[0].source_kind == "warm_start"
    assert rows[0].lifecycle == "sealed"
    assert rows[0].content_identity == rows[0].source_identity
    restarted = normalize_warm_start_minutes(
        batch.model_copy(update={"request_identity": content_hash({"request": "restart"})}),
        completed_before=datetime(2026, 7, 30, 10, 1, tzinfo=SHANGHAI),
    )
    assert restarted[0].session_id == rows[0].session_id
    assert restarted[0].source_identity == rows[0].source_identity


def test_warm_start_wins_exact_l1_overlap_and_conflict_fails_closed() -> None:
    minute = datetime(2026, 7, 30, 10, 0, tzinfo=SHANGHAI)
    warm = _bar(minute, 10).model_copy(update={"source_kind": "warm_start"})
    matching_l1 = _bar(minute, 10).model_copy(
        update={
            "source_kind": "l1",
            "source_identity": content_hash({"source": "l1-match"}),
        }
    )

    assert reconcile_minute_parts((matching_l1, warm)) == (warm,)

    conflict = matching_l1.model_copy(
        update={
            "close": 10.1,
            "source_identity": content_hash({"source": "l1-conflict"}),
        }
    )
    blocked = reconcile_minute_parts((warm, conflict))[0]
    assert blocked.is_complete is False
    assert blocked.known_gaps == ("warm_l1_content_conflict",)


def _bar(minute: datetime, price: float) -> RealtimeMinuteBar:
    identity = content_hash({"minute": minute, "price": price})
    return RealtimeMinuteBar(
        provider="miniqmt",
        session_id=content_hash({"session": "fixture"}),
        instrument_id="600000.SH",
        minute=minute,
        open=price,
        high=price,
        low=price,
        close=price,
        volume=1,
        amount=price,
        observation_count=1,
        source_identity=identity,
        content_identity=identity,
        lifecycle="sealed",
    )


def _provider_row(minute: datetime) -> dict[str, object]:
    return {
        "instrument_id": "600000.SH",
        "time": int(minute.timestamp() * 1000),
        "open": 10.0,
        "high": 10.2,
        "low": 9.9,
        "close": 10.1,
        "volume": 100.0,
        "amount": 1010.0,
    }
