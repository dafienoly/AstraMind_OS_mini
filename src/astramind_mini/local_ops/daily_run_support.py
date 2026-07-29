"""Internal outcomes and deterministic contract builders for WP-0030."""

from __future__ import annotations

import inspect
from collections.abc import Awaitable
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Literal

from .contracts import DailyRunStatus, DailyRunStep, DailyRunStepId, DailyRunSummary
from .identity import operations_hash

POLICY_VERSION = "wp-0030-daily-run-v1.1.0"


@dataclass(frozen=True, slots=True)
class DailyDataOutcome:
    state: Literal["completed", "waiting_provider", "stale", "blocked", "recovery_required"]
    commit_id: str | None = None
    data_snapshot_id: str | None = None
    rotation_snapshot_id: str | None = None
    blocker_codes: tuple[str, ...] = ()
    recovery_action: str | None = None


@dataclass(frozen=True, slots=True)
class DailyDecisionOutcome:
    state: Literal["completed", "blocked", "recovery_required"]
    feature_snapshot_id: str | None = None
    prediction_batch_id: str | None = None
    portfolio_target_id: str | None = None
    order_plan_id: str | None = None
    blocker_codes: tuple[str, ...] = ()
    recovery_action: str | None = None


@dataclass(frozen=True, slots=True)
class BackupReadinessOutcome:
    ready: bool
    backup_id: str | None = None
    blocker_codes: tuple[str, ...] = ()
    recovery_action: str | None = None


@dataclass(frozen=True, slots=True)
class DailyRunResult:
    status: DailyRunStatus
    summary: DailyRunSummary | None = None
    artifact_path: Path | None = None


async def resolve[T](value: T | Awaitable[T]) -> T:
    return await value if inspect.isawaitable(value) else value


def daily_run_id(*, target_date: date, base_snapshot_id: str) -> str:
    digest = operations_hash(
        {
            "target_date": target_date,
            "base_snapshot_id": base_snapshot_id,
            "policy_version": POLICY_VERSION,
        }
    )
    return "daily-run:" + digest.removeprefix("sha256:")


def build_status(**values: object) -> DailyRunStatus:
    values["content_hash"] = operations_hash(values)
    return DailyRunStatus.model_validate(values)


def evolve_status(value: DailyRunStatus, **changes: object) -> DailyRunStatus:
    payload = value.model_dump()
    payload.update(changes)
    payload.pop("content_hash")
    payload["content_hash"] = operations_hash(payload)
    return DailyRunStatus.model_validate(payload)


def build_step(
    run_id: str,
    step_id: DailyRunStepId,
    state: Literal["pending", "running", "completed", "waiting", "blocked"],
    started_at: datetime,
    *,
    updated_at: datetime | None = None,
    completed_at: datetime | None = None,
    output_identity: str | None = None,
    blocker_codes: tuple[str, ...] = (),
    recovery_action: str | None = None,
) -> DailyRunStep:
    values = {
        "run_id": run_id,
        "step_id": step_id,
        "state": state,
        "output_identity": output_identity,
        "blocker_codes": blocker_codes,
        "recovery_action": recovery_action,
        "started_at": started_at,
        "updated_at": updated_at or started_at,
        "completed_at": completed_at,
    }
    values["content_hash"] = operations_hash(values)
    return DailyRunStep.model_validate(values)


def build_summary(
    status: DailyRunStatus, steps: tuple[DailyRunStep, ...], completed_at: datetime
) -> DailyRunSummary:
    required = {
        "data_commit_id": status.data_commit_id,
        "data_snapshot_id": status.data_snapshot_id,
        "rotation_snapshot_id": status.rotation_snapshot_id,
        "feature_snapshot_id": status.feature_snapshot_id,
        "prediction_batch_id": status.prediction_batch_id,
        "portfolio_target_id": status.portfolio_target_id,
        "order_plan_id": status.order_plan_id,
        "backup_id": status.backup_id,
    }
    if any(value is None for value in required.values()):
        raise ValueError("日常运行摘要缺少必要身份")
    identity = {
        "run_id": status.run_id,
        "target_date": status.target_date,
        "base_snapshot_id": status.base_snapshot_id,
        **required,
        "steps": steps,
        "started_at": status.started_at,
        "completed_at": completed_at,
        "paper_dispatch_state": "disabled",
        "broker_connection_attempts": 0,
        "broker_write_attempts": 0,
        "broker_actions_allowed": False,
        "policy_version": POLICY_VERSION,
    }
    digest = operations_hash(identity)
    identity["summary_id"] = "daily-run-summary:" + digest.removeprefix("sha256:")
    identity["content_hash"] = digest
    return DailyRunSummary.model_validate(identity)


__all__ = [
    "BackupReadinessOutcome",
    "DailyDataOutcome",
    "DailyDecisionOutcome",
    "DailyRunResult",
    "build_status",
    "build_step",
    "build_summary",
    "daily_run_id",
    "evolve_status",
    "resolve",
]
