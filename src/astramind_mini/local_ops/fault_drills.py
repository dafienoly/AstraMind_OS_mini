"""Deterministic fail-closed drills for the offline Paper guard."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, cast

from .contracts import OfflineFaultCaseResult, OfflineFaultDrillReport
from .guard_store import GuardLeaseUnavailable, OfflineGuardStore
from .identity import operations_hash
from .offline_guard import (
    LEASE_NAME,
    OfflineDailyGuard,
    OfflineGuardInputs,
    OfflineGuardInterrupted,
)


def run_offline_fault_drills(
    *,
    database: Path,
    logical_date: date,
    started_at: datetime,
) -> OfflineFaultDrillReport:
    if started_at.tzinfo is None:
        raise ValueError("故障演练时间必须带时区")
    store = OfflineGuardStore(database)
    cases = [
        _blocked_case(store, logical_date, started_at, "stale_data", data_fresh=False),
        _blocked_case(
            store,
            logical_date,
            started_at + timedelta(seconds=1),
            "foreign_open_order",
            foreign_open_order_count=1,
        ),
        _blocked_case(
            store,
            logical_date,
            started_at + timedelta(seconds=2),
            "mandate_expired",
            mandate_active=False,
        ),
        _blocked_case(
            store,
            logical_date,
            started_at + timedelta(seconds=3),
            "submission_unknown",
            submission_unknown=True,
        ),
        _blocked_case(
            store,
            logical_date,
            started_at + timedelta(seconds=4),
            "callback_out_of_order",
            callback_order_valid=False,
        ),
        _restart_case(store, logical_date, started_at + timedelta(seconds=5)),
        _duplicate_case(store, started_at + timedelta(seconds=6)),
        _blocked_case(
            store,
            logical_date,
            started_at + timedelta(seconds=7),
            "sqlite_write_failure",
            storage_writable=False,
        ),
    ]
    completed_at = started_at + timedelta(seconds=8)
    status = "passed" if all(case.status == "passed" for case in cases) else "failed"
    blockers = tuple(sorted(case.scenario for case in cases if case.status == "failed"))
    identity = {
        "logical_date": logical_date,
        "started_at": started_at,
        "completed_at": completed_at,
        "status": status,
        "cases": tuple(cases),
        "blocker_codes": blockers,
        "broker_connection_attempts": 0,
        "broker_write_attempts": 0,
        "broker_actions_allowed": False,
    }
    digest = operations_hash(identity)
    report = OfflineFaultDrillReport.model_validate(
        {
            "report_id": "offline-fault-drill:" + digest.removeprefix("sha256:"),
            **identity,
            "content_hash": digest,
        }
    )
    store.publish_drill(report)
    return report


def healthy_inputs() -> OfflineGuardInputs:
    return OfflineGuardInputs(
        backup_id="local-backup:test",
        recovery_report_id="recovery-drill:test",
        data_snapshot_id="data-snapshot:test",
        feature_snapshot_id="feature-snapshot:test",
        prediction_batch_id="prediction-batch:test",
        portfolio_target_id="portfolio-target:test",
        order_plan_id="order-plan:test",
        mandate_preview_id="standing-mandate-preview:test",
    )


def _blocked_case(
    store: OfflineGuardStore,
    logical_date: date,
    at: datetime,
    scenario: str,
    **changes: object,
) -> OfflineFaultCaseResult:
    run = OfflineDailyGuard(store).run(
        logical_date=logical_date,
        owner_id=f"fault-drill:{scenario}",
        inputs=replace(healthy_inputs(), **cast(Any, changes)),
        started_at=at,
    )
    expected = {
        "stale_data": "data_stale",
        "foreign_open_order": "foreign_open_order_present",
        "mandate_expired": "standing_mandate_expired",
        "submission_unknown": "submission_unknown_query_only",
        "callback_out_of_order": "callback_sequence_invalid",
        "sqlite_write_failure": "control_store_unwritable",
    }[scenario]
    recovery = "query_only" if scenario == "submission_unknown" else "operator_action"
    return _case(
        scenario=scenario,
        passed=run.state == "blocked" and expected in run.blocker_codes,
        blockers=run.blocker_codes,
        recovery=recovery,
    )


def _restart_case(
    store: OfflineGuardStore, logical_date: date, at: datetime
) -> OfflineFaultCaseResult:
    guard = OfflineDailyGuard(store)
    inputs = healthy_inputs()
    interrupted = False
    try:
        guard.run(
            logical_date=logical_date,
            owner_id="fault-drill:restart",
            inputs=inputs,
            started_at=at,
            interrupt_after_task="prediction_batch",
        )
    except OfflineGuardInterrupted:
        interrupted = True
    resumed = guard.run(
        logical_date=logical_date,
        owner_id="fault-drill:restart",
        inputs=inputs,
        started_at=at,
    )
    return _case(
        scenario="restart_after_checkpoint",
        passed=interrupted and resumed.state == "completed",
        blockers=(),
        recovery="resume_checkpoint",
    )


def _duplicate_case(store: OfflineGuardStore, at: datetime) -> OfflineFaultCaseResult:
    store.acquire_lease(
        lease_name=LEASE_NAME,
        owner_id="fault-drill:first",
        heartbeat_at=at,
        expires_at=at + timedelta(seconds=30),
    )
    blocked = False
    try:
        store.acquire_lease(
            lease_name=LEASE_NAME,
            owner_id="fault-drill:second",
            heartbeat_at=at + timedelta(seconds=1),
            expires_at=at + timedelta(seconds=31),
        )
    except GuardLeaseUnavailable:
        blocked = True
    finally:
        store.release_lease(lease_name=LEASE_NAME, owner_id="fault-drill:first")
    return _case(
        scenario="duplicate_instance",
        passed=blocked,
        blockers=("duplicate_guard_instance",) if blocked else (),
        recovery="operator_action",
    )


def _case(
    *,
    scenario: str,
    passed: bool,
    blockers: tuple[str, ...],
    recovery: str,
) -> OfflineFaultCaseResult:
    identity = {
        "scenario": scenario,
        "status": "passed" if passed else "failed",
        "observed_blocker_codes": blockers,
        "duplicate_side_effect_count": 0,
        "recovery_mode": recovery,
        "broker_actions_allowed": False,
    }
    return OfflineFaultCaseResult.model_validate(
        {**identity, "content_hash": operations_hash(identity)}
    )


__all__ = ["healthy_inputs", "run_offline_fault_drills"]
