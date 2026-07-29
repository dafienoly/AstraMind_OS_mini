from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable, Coroutine
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from astramind_mini.local_ops.daily_run import (
    BackupReadinessOutcome,
    DailyDataOutcome,
    DailyDecisionOutcome,
    DailyRunOrchestrator,
    DailyRunResult,
    daily_run_id,
)
from astramind_mini.local_ops.daily_run_store import (
    DailyRunLeaseUnavailable,
    DailyRunStore,
)

SHANGHAI = ZoneInfo("Asia/Shanghai")
NOW = datetime(2026, 7, 28, 20, 30, tzinfo=SHANGHAI)
TARGET = date(2026, 7, 28)
BASE = "snapshot:base"


def run(value: Coroutine[Any, Any, DailyRunResult]) -> DailyRunResult:
    return asyncio.run(value)


def store(tmp_path: Path) -> DailyRunStore:
    return DailyRunStore(
        tmp_path / "control" / "local-ops.sqlite3",
        tmp_path / "artifacts",
    )


def data_current() -> DailyDataOutcome:
    return DailyDataOutcome(
        state="completed",
        commit_id="daily-commit:one",
        data_snapshot_id="snapshot:one",
        rotation_snapshot_id="rotation:one",
    )


def decision_current() -> DailyDecisionOutcome:
    return DailyDecisionOutcome(
        state="completed",
        feature_snapshot_id="feature:one",
        prediction_batch_id="prediction:one",
        portfolio_target_id="target:one",
        order_plan_id="order-plan:one",
    )


def backup_ready() -> BackupReadinessOutcome:
    return BackupReadinessOutcome(ready=True, backup_id="local-backup:one")


def orchestrator(
    control: DailyRunStore,
    *,
    run_data: Callable[[], DailyDataOutcome | Awaitable[DailyDataOutcome]] = data_current,
    run_decision: Callable[
        [], DailyDecisionOutcome | Awaitable[DailyDecisionOutcome]
    ] = decision_current,
    check_backup: Callable[
        [], BackupReadinessOutcome | Awaitable[BackupReadinessOutcome]
    ] = backup_ready,
    clock: Callable[[], datetime] = lambda: NOW,
) -> DailyRunOrchestrator:
    return DailyRunOrchestrator(
        store=control,
        run_data=run_data,
        run_decision=run_decision,
        check_backup=check_backup,
        clock=clock,
    )


def test_success_publishes_one_immutable_summary_and_reuses_it(tmp_path: Path) -> None:
    control = store(tmp_path)
    calls = {"data": 0, "decision": 0, "backup": 0}

    def data() -> DailyDataOutcome:
        calls["data"] += 1
        return data_current()

    def decision() -> DailyDecisionOutcome:
        calls["decision"] += 1
        return decision_current()

    def backup() -> BackupReadinessOutcome:
        calls["backup"] += 1
        return backup_ready()

    service = orchestrator(
        control,
        run_data=data,
        run_decision=decision,
        check_backup=backup,
    )
    first = run(service.run(target_date=TARGET, base_snapshot_id=BASE))
    second = run(service.run(target_date=TARGET, base_snapshot_id=BASE))

    assert first.status.state == "current"
    assert first.summary == second.summary
    assert calls == {"data": 1, "decision": 1, "backup": 1}
    assert first.summary is not None
    assert first.summary.paper_dispatch_state == "disabled"
    assert first.summary.broker_connection_attempts == 0
    assert first.summary.broker_write_attempts == 0
    assert not first.summary.broker_actions_allowed
    assert [step.step_id for step in first.summary.steps] == [
        "data_pipeline",
        "decision_chain",
        "backup_readiness",
    ]
    pointer = json.loads((tmp_path / "artifacts" / "current.json").read_text())
    assert pointer["run_id"] == first.status.run_id


def test_explicit_recovery_reopens_current_run_and_archives_summary(
    tmp_path: Path,
) -> None:
    control = store(tmp_path)
    calls = {"data": 0, "decision": 0, "backup": 0}

    def data() -> DailyDataOutcome:
        calls["data"] += 1
        suffix = calls["data"]
        return DailyDataOutcome(
            state="completed",
            commit_id=f"daily-commit:{suffix}",
            data_snapshot_id=f"snapshot:{suffix}",
            rotation_snapshot_id=f"rotation:{suffix}",
        )

    def decision() -> DailyDecisionOutcome:
        calls["decision"] += 1
        suffix = calls["decision"]
        return DailyDecisionOutcome(
            state="completed",
            feature_snapshot_id=f"feature:{suffix}",
            prediction_batch_id=f"prediction:{suffix}",
            portfolio_target_id=f"target:{suffix}",
            order_plan_id=f"order-plan:{suffix}",
        )

    def backup() -> BackupReadinessOutcome:
        calls["backup"] += 1
        return BackupReadinessOutcome(
            ready=True,
            backup_id=f"local-backup:{calls['backup']}",
        )

    service = orchestrator(
        control,
        run_data=data,
        run_decision=decision,
        check_backup=backup,
    )
    first = run(service.run(target_date=TARGET, base_snapshot_id=BASE))
    recovered = run(service.run(target_date=TARGET, base_snapshot_id=BASE, recover=True))

    assert first.status.run_id == recovered.status.run_id
    assert first.summary is not None and recovered.summary is not None
    assert first.summary.summary_id != recovered.summary.summary_id
    assert calls == {"data": 2, "decision": 2, "backup": 2}
    assert control.summary_history(first.status.run_id) == (first.summary,)


def test_waiting_provider_does_not_advance_decision_or_pointer(tmp_path: Path) -> None:
    control = store(tmp_path)
    completed = run(
        orchestrator(control).run(
            target_date=date(2026, 7, 27),
            base_snapshot_id="snapshot:previous",
        )
    )
    decision_calls = 0

    def waiting() -> DailyDataOutcome:
        return DailyDataOutcome(
            state="waiting_provider",
            blocker_codes=("events_not_complete",),
            recovery_action="20:05 后恢复",
        )

    def decision() -> DailyDecisionOutcome:
        nonlocal decision_calls
        decision_calls += 1
        return decision_current()

    later = orchestrator(control, run_data=waiting, run_decision=decision)
    result = run(
        later.run(
            target_date=TARGET,
            base_snapshot_id="snapshot:next",
            recover=True,
        )
    )

    assert result.status.state == "waiting_provider"
    assert result.summary is None
    assert decision_calls == 0
    pointer = json.loads((tmp_path / "artifacts" / "current.json").read_text())
    assert pointer["run_id"] == completed.status.run_id


def test_recovery_reuses_completed_data_step(tmp_path: Path) -> None:
    control = store(tmp_path)
    calls = {"data": 0, "decision": 0}

    def data() -> DailyDataOutcome:
        calls["data"] += 1
        return data_current()

    def interrupted_decision() -> DailyDecisionOutcome:
        calls["decision"] += 1
        raise RuntimeError("synthetic interruption")

    first = orchestrator(control, run_data=data, run_decision=interrupted_decision)
    interrupted = run(first.run(target_date=TARGET, base_snapshot_id=BASE))
    assert interrupted.status.state == "recovery_required"

    def recovered_decision() -> DailyDecisionOutcome:
        calls["decision"] += 1
        return decision_current()

    recovered = orchestrator(control, run_data=data, run_decision=recovered_decision)
    result = run(recovered.run(target_date=TARGET, base_snapshot_id=BASE, recover=True))

    assert result.status.state == "current"
    assert calls == {"data": 1, "decision": 2}
    assert result.status.data_commit_id == "daily-commit:one"
    assert result.status.order_plan_id == "order-plan:one"


def test_backup_not_ready_is_visible_and_recoverable(tmp_path: Path) -> None:
    control = store(tmp_path)
    service = orchestrator(
        control,
        check_backup=lambda: BackupReadinessOutcome(
            ready=False,
            blocker_codes=("daily_backup_not_ready",),
            recovery_action="运行备份后恢复",
        ),
    )

    result = run(service.run(target_date=TARGET, base_snapshot_id=BASE))

    assert result.status.state == "blocked"
    assert result.status.current_step == "backup_readiness"
    assert result.status.blocker_codes == ("daily_backup_not_ready",)
    assert result.summary is None
    assert not (tmp_path / "artifacts" / "current.json").exists()


def test_live_lease_rejects_competing_instance(tmp_path: Path) -> None:
    control = store(tmp_path)
    run_id = daily_run_id(target_date=TARGET, base_snapshot_id=BASE)
    control.acquire_lease(
        run_id=run_id,
        owner_id="first-owner",
        acquired_at=NOW,
        expires_at=NOW + timedelta(minutes=5),
    )

    with pytest.raises(DailyRunLeaseUnavailable):
        run(orchestrator(control).run(target_date=TARGET, base_snapshot_id=BASE))


def test_before_window_waits_without_calling_upstream(tmp_path: Path) -> None:
    control = store(tmp_path)
    called = False

    def data() -> DailyDataOutcome:
        nonlocal called
        called = True
        return data_current()

    before_close = datetime(2026, 7, 28, 15, 59, tzinfo=SHANGHAI)
    result = run(
        orchestrator(control, run_data=data, clock=lambda: before_close).run(
            target_date=TARGET,
            base_snapshot_id=BASE,
        )
    )

    assert result.status.state == "waiting_window"
    assert not called


def test_budget_exhaustion_fails_closed_before_next_step(tmp_path: Path) -> None:
    control = store(tmp_path)
    moments = iter(
        [
            NOW,
            NOW,
            NOW,
            NOW,
            NOW + timedelta(minutes=31),
            NOW + timedelta(minutes=31),
        ]
    )
    decision_called = False

    def decision() -> DailyDecisionOutcome:
        nonlocal decision_called
        decision_called = True
        return decision_current()

    service = orchestrator(
        control,
        run_decision=decision,
        clock=lambda: next(moments),
    )
    result = run(service.run(target_date=TARGET, base_snapshot_id=BASE))

    assert result.status.state == "stale"
    assert result.status.blocker_codes == ("daily_budget_exhausted",)
    assert not decision_called

    recovery_time = NOW + timedelta(minutes=32)
    recovered = run(
        orchestrator(
            control,
            run_decision=decision,
            clock=lambda: recovery_time,
        ).run(
            target_date=TARGET,
            base_snapshot_id=BASE,
            recover=True,
        )
    )

    assert recovered.status.state == "current"
    assert recovered.status.run_id == result.status.run_id
    assert decision_called
