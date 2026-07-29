"""Upstream step execution and resumable checkpoints for WP-0030."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta
from typing import Literal

from .contracts import DailyRunState, DailyRunStatus, DailyRunStepId
from .daily_run_store import DailyRunStore
from .daily_run_support import (
    BackupReadinessOutcome,
    DailyDataOutcome,
    DailyDecisionOutcome,
    build_step,
    evolve_status,
    resolve,
)


class DailyRunStepExecutor:
    def __init__(
        self,
        *,
        store: DailyRunStore,
        run_data: Callable[[], DailyDataOutcome | Awaitable[DailyDataOutcome]],
        run_decision: Callable[[], DailyDecisionOutcome | Awaitable[DailyDecisionOutcome]],
        check_backup: Callable[[], BackupReadinessOutcome | Awaitable[BackupReadinessOutcome]],
        clock: Callable[[], datetime],
    ) -> None:
        self._store = store
        self._run_data = run_data
        self._run_decision = run_decision
        self._check_backup = check_backup
        self._clock = clock

    async def execute_data(self, status: DailyRunStatus) -> tuple[DailyRunStatus, bool]:
        status = self._start(status, "data_pipeline")
        if status.state == "stale":
            return status, True
        try:
            outcome = await resolve(self._run_data())
        except Exception:
            return self._interrupt(status, "data_pipeline", "data_pipeline_interrupted")
        if outcome.state != "completed":
            state: DailyRunState = outcome.state
            return (
                self._stop(
                    status,
                    "data_pipeline",
                    state="waiting" if state == "waiting_provider" else "blocked",
                    run_state=state,
                    blockers=outcome.blocker_codes,
                    recovery_action=outcome.recovery_action,
                ),
                True,
            )
        required = (outcome.commit_id, outcome.data_snapshot_id, outcome.rotation_snapshot_id)
        if any(value is None for value in required):
            return self._interrupt(status, "data_pipeline", "data_pipeline_identity_missing")
        completed = self._complete(status, "data_pipeline", str(outcome.commit_id))
        return (
            evolve_status(
                completed,
                data_commit_id=outcome.commit_id,
                data_snapshot_id=outcome.data_snapshot_id,
                rotation_snapshot_id=outcome.rotation_snapshot_id,
            ),
            False,
        )

    async def execute_decision(self, status: DailyRunStatus) -> tuple[DailyRunStatus, bool]:
        status = self._start(status, "decision_chain")
        if status.state == "stale":
            return status, True
        try:
            outcome = await resolve(self._run_decision())
        except Exception:
            return self._interrupt(status, "decision_chain", "decision_chain_interrupted")
        if outcome.state != "completed":
            return (
                self._stop(
                    status,
                    "decision_chain",
                    state="blocked",
                    run_state=outcome.state,
                    blockers=outcome.blocker_codes,
                    recovery_action=outcome.recovery_action,
                ),
                True,
            )
        identities = (
            outcome.feature_snapshot_id,
            outcome.prediction_batch_id,
            outcome.portfolio_target_id,
            outcome.order_plan_id,
        )
        if any(value is None for value in identities):
            return self._interrupt(status, "decision_chain", "decision_chain_identity_missing")
        completed = self._complete(status, "decision_chain", str(outcome.order_plan_id))
        return (
            evolve_status(
                completed,
                feature_snapshot_id=outcome.feature_snapshot_id,
                prediction_batch_id=outcome.prediction_batch_id,
                portfolio_target_id=outcome.portfolio_target_id,
                order_plan_id=outcome.order_plan_id,
            ),
            False,
        )

    async def execute_backup(self, status: DailyRunStatus) -> tuple[DailyRunStatus, bool]:
        status = self._start(status, "backup_readiness")
        if status.state == "stale":
            return status, True
        try:
            outcome = await resolve(self._check_backup())
        except Exception:
            return self._interrupt(status, "backup_readiness", "backup_check_interrupted")
        if not outcome.ready or not outcome.backup_id:
            return (
                self._stop(
                    status,
                    "backup_readiness",
                    state="blocked",
                    run_state="blocked",
                    blockers=outcome.blocker_codes or ("backup_not_ready",),
                    recovery_action=outcome.recovery_action or "运行 make ops-backup 后恢复",
                ),
                True,
            )
        completed = self._complete(status, "backup_readiness", outcome.backup_id)
        return evolve_status(completed, backup_id=outcome.backup_id), False

    def _start(self, status: DailyRunStatus, step_id: DailyRunStepId) -> DailyRunStatus:
        now = self._now()
        if now - status.started_at > timedelta(minutes=status.daily_budget_minutes):
            stale = evolve_status(
                status,
                state="stale",
                current_step=step_id,
                updated_at=now,
                blocker_codes=("daily_budget_exhausted",),
                recovery_action="检查上游状态后运行 make daily-run-recover",
            )
            self._store.publish_status(stale)
            return stale
        self._store.publish_step(build_step(status.run_id, step_id, "running", now))
        running = evolve_status(status, state="running", current_step=step_id, updated_at=now)
        self._store.publish_status(running)
        return running

    def _complete(
        self, status: DailyRunStatus, step_id: DailyRunStepId, output_identity: str
    ) -> DailyRunStatus:
        now = self._now()
        existing = self._store.step(status.run_id, step_id)
        self._store.publish_step(
            build_step(
                status.run_id,
                step_id,
                "completed",
                existing.started_at if existing else now,
                updated_at=now,
                completed_at=now,
                output_identity=output_identity,
            )
        )
        return evolve_status(status, updated_at=now)

    def _stop(
        self,
        status: DailyRunStatus,
        step_id: DailyRunStepId,
        *,
        state: Literal["waiting", "blocked"],
        run_state: DailyRunState,
        blockers: tuple[str, ...],
        recovery_action: str | None,
    ) -> DailyRunStatus:
        now = self._now()
        existing = self._store.step(status.run_id, step_id)
        self._store.publish_step(
            build_step(
                status.run_id,
                step_id,
                state,
                existing.started_at if existing else now,
                updated_at=now,
                blocker_codes=blockers,
                recovery_action=recovery_action,
            )
        )
        stopped = evolve_status(
            status,
            state=run_state,
            current_step=step_id,
            updated_at=now,
            blocker_codes=blockers,
            recovery_action=recovery_action,
        )
        self._store.publish_status(stopped)
        return stopped

    def _interrupt(
        self, status: DailyRunStatus, step_id: DailyRunStepId, blocker: str
    ) -> tuple[DailyRunStatus, bool]:
        return (
            self._stop(
                status,
                step_id,
                state="blocked",
                run_state="recovery_required",
                blockers=(blocker,),
                recovery_action="运行 make daily-run-recover 复用同一运行身份",
            ),
            True,
        )

    def _now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None:
            raise ValueError("日常运行时钟必须带时区")
        return value


__all__ = ["DailyRunStepExecutor"]
