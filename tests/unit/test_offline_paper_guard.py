from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, cast

import pytest

from astramind_mini.local_ops import (
    GuardLeaseUnavailable,
    OfflineDailyGuard,
    OfflineGuardStore,
    run_offline_fault_drills,
)
from astramind_mini.local_ops.fault_drills import healthy_inputs
from astramind_mini.local_ops.offline_guard import (
    LEASE_NAME,
    OfflineGuardInterrupted,
)

NOW = datetime(2026, 7, 28, 8, tzinfo=UTC)
DAY = date(2026, 7, 28)


def test_offline_guard_completes_chain_but_permanently_disables_dispatch(
    tmp_path: Path,
) -> None:
    guard = OfflineDailyGuard(OfflineGuardStore(tmp_path / "local-ops.sqlite3"))
    run = guard.run(
        logical_date=DAY,
        owner_id="offline-paper-guard:2026-07-28",
        inputs=healthy_inputs(),
        started_at=NOW,
    )
    repeated = guard.run(
        logical_date=DAY,
        owner_id="another-process-after-completion",
        inputs=healthy_inputs(),
        started_at=NOW + timedelta(minutes=1),
    )

    assert repeated == run
    assert run.state == "completed"
    assert run.paper_dispatch_state == "disabled"
    assert run.broker_actions_allowed is False
    assert [item.task_id for item in run.task_results][-1] == "paper_dispatch_disabled"
    assert all(item.broker_actions_allowed is False for item in run.task_results)


@pytest.mark.parametrize(
    ("changes", "expected"),
    [
        ({"data_fresh": False}, "data_stale"),
        ({"foreign_open_order_count": 1}, "foreign_open_order_present"),
        ({"mandate_active": False}, "standing_mandate_expired"),
        ({"submission_unknown": True}, "submission_unknown_query_only"),
        ({"callback_order_valid": False}, "callback_sequence_invalid"),
        ({"storage_writable": False}, "control_store_unwritable"),
    ],
)
def test_offline_guard_fails_closed(
    tmp_path: Path, changes: dict[str, object], expected: str
) -> None:
    run = OfflineDailyGuard(OfflineGuardStore(tmp_path / f"{expected}.sqlite3")).run(
        logical_date=DAY,
        owner_id=f"test:{expected}",
        inputs=replace(healthy_inputs(), **cast(Any, changes)),
        started_at=NOW,
    )

    assert run.state == "blocked"
    assert expected in run.blocker_codes
    assert run.broker_actions_allowed is False
    assert any(item.state == "skipped" for item in run.task_results)


def test_restart_resumes_durable_checkpoints_without_duplicate_tasks(
    tmp_path: Path,
) -> None:
    store = OfflineGuardStore(tmp_path / "local-ops.sqlite3")
    guard = OfflineDailyGuard(store)
    with pytest.raises(OfflineGuardInterrupted):
        guard.run(
            logical_date=DAY,
            owner_id="test:restart",
            inputs=healthy_inputs(),
            started_at=NOW,
            interrupt_after_task="prediction_batch",
        )

    run = guard.run(
        logical_date=DAY,
        owner_id="test:restart",
        inputs=healthy_inputs(),
        started_at=NOW + timedelta(seconds=5),
    )
    assert run.state == "completed"
    assert len(run.task_results) == len({item.task_id for item in run.task_results})


def test_non_expired_lease_blocks_second_instance(tmp_path: Path) -> None:
    store = OfflineGuardStore(tmp_path / "local-ops.sqlite3")
    store.acquire_lease(
        lease_name=LEASE_NAME,
        owner_id="first",
        heartbeat_at=NOW,
        expires_at=NOW + timedelta(seconds=30),
    )
    with pytest.raises(GuardLeaseUnavailable):
        store.acquire_lease(
            lease_name=LEASE_NAME,
            owner_id="second",
            heartbeat_at=NOW + timedelta(seconds=1),
            expires_at=NOW + timedelta(seconds=31),
        )


def test_fault_drill_covers_all_fail_closed_scenarios(tmp_path: Path) -> None:
    report = run_offline_fault_drills(
        database=tmp_path / "local-ops.sqlite3",
        logical_date=DAY,
        started_at=NOW,
    )

    assert report.status == "passed"
    assert len(report.cases) == 8
    assert all(item.status == "passed" for item in report.cases)
    assert report.broker_connection_attempts == 0
    assert report.broker_write_attempts == 0
    assert report.broker_actions_allowed is False
