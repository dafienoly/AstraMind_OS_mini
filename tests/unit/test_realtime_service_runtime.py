from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from astramind_mini.local_ops.realtime_service_runtime import (
    RealtimeServiceLock,
    RealtimeStatusStore,
    active_capture_deadline,
    realtime_session_state,
    retained_open_dates,
)


def test_capture_window_uses_shanghai_trading_date() -> None:
    open_dates = (date(2026, 7, 29),)

    active = active_capture_deadline(
        datetime(2026, 7, 29, 1, 0, tzinfo=UTC),
        open_dates,
    )

    assert active is not None
    market_date, deadline = active
    assert market_date == date(2026, 7, 29)
    assert deadline.hour == 16
    assert deadline.minute == 5
    assert (
        active_capture_deadline(
            datetime(2026, 7, 29, 8, 6, tzinfo=UTC),
            open_dates,
        )
        is None
    )


def test_runtime_names_preopen_lunch_capture_and_sealing_phases() -> None:
    assert realtime_session_state(datetime(2026, 7, 30, 1, 0, tzinfo=UTC)) == "preopen"
    assert realtime_session_state(datetime(2026, 7, 30, 3, 0, tzinfo=UTC)) == "capturing"
    assert realtime_session_state(datetime(2026, 7, 30, 4, 0, tzinfo=UTC)) == "lunch_break"
    assert realtime_session_state(datetime(2026, 7, 30, 7, 1, tzinfo=UTC)) == "sealing"


def test_retention_keeps_last_five_open_dates_only() -> None:
    open_dates = tuple(date(2026, 7, day) for day in range(20, 30))

    retained = retained_open_dates(open_dates, date(2026, 7, 27))

    assert retained == frozenset(
        {
            date(2026, 7, 23),
            date(2026, 7, 24),
            date(2026, 7, 25),
            date(2026, 7, 26),
            date(2026, 7, 27),
        }
    )


def test_runtime_status_is_atomic_and_lock_rejects_duplicate(tmp_path: Path) -> None:
    status_store = RealtimeStatusStore(tmp_path)
    status_store.publish("waiting", market_date=date(2026, 7, 29))

    status = status_store.read()

    assert status is not None
    assert status.state == "waiting"
    assert status.process_state == "running"
    assert status.feed_state == "not_started"
    assert status.last_successful_heartbeat_at is not None
    assert status.log_path is not None
    assert status.market_date == "2026-07-29"
    with (
        RealtimeServiceLock(tmp_path),
        pytest.raises(RuntimeError, match="already_running"),
        RealtimeServiceLock(tmp_path),
    ):
        pass
    assert (tmp_path / "service.lock").exists()


def test_runtime_status_retains_bounded_retry_root_causes(tmp_path: Path) -> None:
    failures = tuple(
        {"attempt": index, "error_code": f"specific_{index}", "detail": "bridge stderr"}
        for index in range(1, 7)
    )
    store = RealtimeStatusStore(tmp_path)

    store.publish(
        "blocked",
        feed_state="blocked",
        projection_state="blocked",
        exit_code=2,
        last_error="specific_6",
        retry_failures=failures,
        recovery_action="检查 bridge stderr",
    )

    status = store.read()
    assert status is not None
    assert [item["error_code"] for item in status.retry_failures] == [
        "specific_3",
        "specific_4",
        "specific_5",
        "specific_6",
    ]
    assert status.exit_code == 2
    assert status.recovery_action == "检查 bridge stderr"
