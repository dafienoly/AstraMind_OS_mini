from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

from astramind_mini.local_ops.contracts import DailyRunStatus
from astramind_mini.local_ops.daily_schedule_deployment import (
    TASK_NAME,
    DailyTaskSpec,
    task_xml,
)
from astramind_mini.local_ops.daily_scheduler import evaluate_daily_schedule
from astramind_mini.local_ops.daily_scheduler_store import DailySchedulerStore

HASH = "sha256:" + "1" * 64
OPEN_DATES = (
    date(2026, 7, 27),
    date(2026, 7, 28),
    date(2026, 7, 29),
    date(2026, 7, 30),
)


def status(state: str, target: date = date(2026, 7, 28)) -> DailyRunStatus:
    return DailyRunStatus.model_validate(
        {
            "run_id": f"daily-run:{target.isoformat()}",
            "target_date": target,
            "base_snapshot_id": "snapshot:test",
            "state": state,
            "blocker_codes": ("synthetic_blocker",) if state == "stale" else (),
            "started_at": datetime(2026, 7, 28, 8, tzinfo=UTC),
            "updated_at": datetime(2026, 7, 28, 8, tzinfo=UTC),
            "content_hash": HASH,
        }
    )


def test_post_close_starts_only_latest_open_date() -> None:
    decision = evaluate_daily_schedule(
        open_dates=OPEN_DATES,
        evaluated_at=datetime.fromisoformat("2026-07-28T16:35:00+08:00"),
        latest_run=None,
    )

    assert decision.target_date == date(2026, 7, 28)
    assert decision.trigger == "post_close_1635"
    assert decision.action == "run"
    assert decision.next_trigger_at == datetime.fromisoformat("2026-07-28T16:50:00+08:00")
    assert not decision.broker_actions_allowed


def test_provider_retry_recovers_same_run_identity() -> None:
    decision = evaluate_daily_schedule(
        open_dates=OPEN_DATES,
        evaluated_at=datetime.fromisoformat("2026-07-28T16:50:00+08:00"),
        latest_run=status("waiting_provider"),
    )

    assert decision.trigger == "provider_retry_1650"
    assert decision.action == "recover"
    assert decision.run_id == "daily-run:2026-07-28"


def test_final_trigger_recovers_after_etf_and_event_publish_windows() -> None:
    decision = evaluate_daily_schedule(
        open_dates=OPEN_DATES,
        evaluated_at=datetime.fromisoformat("2026-07-28T20:10:00+08:00"),
        latest_run=status("waiting_provider"),
    )

    assert decision.trigger == "finalize_2010"
    assert decision.action == "recover"
    assert decision.target_date == date(2026, 7, 28)


def test_current_or_stale_run_is_not_automatically_reexecuted() -> None:
    current = evaluate_daily_schedule(
        open_dates=OPEN_DATES,
        evaluated_at=datetime.fromisoformat("2026-07-28T17:10:00+08:00"),
        latest_run=status("current"),
    )
    stale = evaluate_daily_schedule(
        open_dates=OPEN_DATES,
        evaluated_at=datetime.fromisoformat("2026-07-28T17:10:00+08:00"),
        latest_run=status("stale"),
    )

    assert current.action == "view"
    assert current.reason_code == "daily_run_already_current"
    assert stale.action == "view"
    assert stale.reason_code == "manual_attention_required"
    assert stale.blocker_codes == ("synthetic_blocker",)


def test_next_startup_recovers_only_latest_incomplete_trading_day() -> None:
    decision = evaluate_daily_schedule(
        open_dates=OPEN_DATES,
        evaluated_at=datetime.fromisoformat("2026-07-29T08:30:00+08:00"),
        latest_run=status("recovery_required"),
    )

    assert decision.target_date == date(2026, 7, 28)
    assert decision.trigger == "startup_0830"
    assert decision.action == "recover"


def test_request_registration_is_idempotent(tmp_path: Path) -> None:
    store = DailySchedulerStore(tmp_path / "local-ops.sqlite3")
    created_at = datetime.fromisoformat("2026-07-29T08:35:00+08:00")

    first = store.register_request(
        action="recover",
        target_date=date(2026, 7, 28),
        run_id="daily-run:test",
        created_at=created_at,
    )
    second = store.register_request(
        action="recover",
        target_date=date(2026, 7, 28),
        run_id="daily-run:test",
        created_at=created_at,
    )

    assert first == second
    claimed = store.claim_pending(created_at)
    assert claimed is not None
    assert claimed.state == "claimed"


def test_windows_task_definition_is_reviewable_and_broker_free(tmp_path: Path) -> None:
    spec = DailyTaskSpec(
        task_name=TASK_NAME,
        distro="Ubuntu",
        repository_root=Path("/home/ly/work/AstraMind_OS_mini"),
        provider_env_file=Path("/mnt/e/work/AstraMind_OS/.env"),
    )
    payload = task_xml(spec).decode("utf-16")

    assert payload.count("CalendarTrigger") == 10
    assert payload.count("LogonTrigger") == 2
    assert "StartWhenAvailable" in payload
    assert "MultipleInstancesPolicy" in payload
    assert "daily-schedule-trigger" in payload
    assert "/home/ly/work/AstraMind_OS_mini" in payload
    assert "/bin/bash" in payload
    assert "-lc" in payload
    assert all(
        forbidden not in payload.lower()
        for forbidden in (
            "to" + "ken=",
            "account" + "_id",
            "paper-canary",
            "miniqmt",
            "order_stock",
        )
    )
