"""Broker-free unified daily-run orchestration for WP-0030."""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from .contracts import DailyRunState, DailyRunStatus, DailyRunStep, DailyRunStepId
from .daily_run_steps import DailyRunStepExecutor
from .daily_run_store import DailyRunStore
from .daily_run_support import (
    BackupReadinessOutcome,
    DailyDataOutcome,
    DailyDecisionOutcome,
    DailyRunResult,
    build_status,
    build_summary,
    daily_run_id,
    evolve_status,
)

SHANGHAI = ZoneInfo("Asia/Shanghai")


class DailyRunOrchestrator:
    def __init__(
        self,
        *,
        store: DailyRunStore,
        run_data: Callable[[], DailyDataOutcome | Awaitable[DailyDataOutcome]],
        run_decision: Callable[[], DailyDecisionOutcome | Awaitable[DailyDecisionOutcome]],
        check_backup: Callable[[], BackupReadinessOutcome | Awaitable[BackupReadinessOutcome]],
        clock: Callable[[], datetime] = lambda: datetime.now(SHANGHAI),
    ) -> None:
        self._store = store
        self._clock = clock
        self._steps = DailyRunStepExecutor(
            store=store,
            run_data=run_data,
            run_decision=run_decision,
            check_backup=check_backup,
            clock=clock,
        )

    async def run(
        self,
        *,
        target_date: date,
        base_snapshot_id: str,
        recover: bool = False,
    ) -> DailyRunResult:
        now = self._now()
        run_id = daily_run_id(target_date=target_date, base_snapshot_id=base_snapshot_id)
        existing = self._store.status(run_id)
        if existing and existing.state == "current" and not recover:
            return DailyRunResult(status=existing, summary=self._store.summary(run_id))
        if target_date > now.date():
            return self._publish_terminal(
                run_id=run_id,
                target_date=target_date,
                base_snapshot_id=base_snapshot_id,
                existing=existing,
                state="blocked",
                blockers=("target_date_in_future",),
                recovery_action="选择已完成或可恢复的交易日",
            )
        before_post_close = now.timetz().replace(tzinfo=None) < time(16, 30)
        if target_date == now.date() and before_post_close and not recover:
            return self._publish_terminal(
                run_id=run_id,
                target_date=target_date,
                base_snapshot_id=base_snapshot_id,
                existing=existing,
                state="waiting_window",
                blockers=("post_close_window_not_open",),
                recovery_action="16:30 后重新运行 make daily-run",
            )

        owner_id = f"daily-run-owner:{uuid.uuid4().hex}"
        self._store.acquire_lease(
            run_id=run_id,
            owner_id=owner_id,
            acquired_at=now,
            expires_at=now + timedelta(minutes=30),
        )
        try:
            if existing and existing.state == "current" and recover:
                self._store.prepare_recovery(run_id, now)
            return await self._run_locked(
                run_id=run_id,
                target_date=target_date,
                base_snapshot_id=base_snapshot_id,
                existing=existing,
                recover=recover,
            )
        finally:
            self._store.release_lease(run_id=run_id, owner_id=owner_id)

    async def _run_locked(
        self,
        *,
        run_id: str,
        target_date: date,
        base_snapshot_id: str,
        existing: DailyRunStatus | None,
        recover: bool,
    ) -> DailyRunResult:
        reset_attempt_budget = bool(existing and (recover or existing.state == "waiting_provider"))
        started_at = (
            self._now()
            if reset_attempt_budget
            else existing.started_at
            if existing
            else self._now()
        )
        status = (
            self._status_from(
                existing,
                state="running",
                current_step=None,
                started_at=started_at,
                updated_at=self._now(),
                completed_at=None,
                blocker_codes=(),
                recovery_action=None,
            )
            if existing
            else self._status(
                run_id=run_id,
                target_date=target_date,
                base_snapshot_id=base_snapshot_id,
                started_at=started_at,
                state="running",
            )
        )
        self._store.publish_status(status)

        data_step = self._store.step(run_id, "data_pipeline")
        if not data_step or data_step.state != "completed":
            status, early = await self._steps.execute_data(status)
            if early:
                return DailyRunResult(status=status)

        decision_step = self._store.step(run_id, "decision_chain")
        if not decision_step or decision_step.state != "completed":
            status, early = await self._steps.execute_decision(status)
            if early:
                return DailyRunResult(status=status)

        backup_step = self._store.step(run_id, "backup_readiness")
        if not backup_step or backup_step.state != "completed":
            status, early = await self._steps.execute_backup(status)
            if early:
                return DailyRunResult(status=status)

        step_ids: tuple[DailyRunStepId, ...] = (
            "data_pipeline",
            "decision_chain",
            "backup_readiness",
        )
        steps = tuple(self._required_step(run_id, step_id) for step_id in step_ids)
        completed_at = self._now()
        summary = build_summary(status, steps, completed_at)
        path = self._store.publish_summary(summary)
        current = self._status_from(
            status,
            state="current",
            current_step=None,
            completed_at=completed_at,
            updated_at=completed_at,
            blocker_codes=(),
            recovery_action=None,
        )
        self._store.publish_status(current)
        return DailyRunResult(status=current, summary=summary, artifact_path=path)

    def _publish_terminal(
        self,
        *,
        run_id: str,
        target_date: date,
        base_snapshot_id: str,
        existing: DailyRunStatus | None,
        state: DailyRunState,
        blockers: tuple[str, ...],
        recovery_action: str,
    ) -> DailyRunResult:
        now = self._now()
        status = self._status(
            run_id=run_id,
            target_date=target_date,
            base_snapshot_id=base_snapshot_id,
            started_at=existing.started_at if existing else now,
            state=state,
            blockers=blockers,
            recovery_action=recovery_action,
        )
        self._store.publish_status(status)
        return DailyRunResult(status=status)

    def _status(
        self,
        *,
        run_id: str,
        target_date: date,
        base_snapshot_id: str,
        started_at: datetime,
        state: DailyRunState,
        blockers: tuple[str, ...] = (),
        recovery_action: str | None = None,
    ) -> DailyRunStatus:
        return build_status(
            run_id=run_id,
            target_date=target_date,
            base_snapshot_id=base_snapshot_id,
            started_at=started_at,
            updated_at=self._now(),
            state=state,
            blocker_codes=blockers,
            recovery_action=recovery_action,
        )

    @staticmethod
    def _status_from(value: DailyRunStatus, **changes: object) -> DailyRunStatus:
        return evolve_status(value, **changes)

    def _required_step(self, run_id: str, step_id: DailyRunStepId) -> DailyRunStep:
        value = self._store.step(run_id, step_id)
        if value is None or value.state != "completed":
            raise ValueError(f"日常运行步骤未完成：{step_id}")
        return value

    def _now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None:
            raise ValueError("日常运行时钟必须带时区")
        return value


__all__ = [
    "BackupReadinessOutcome",
    "DailyDataOutcome",
    "DailyDecisionOutcome",
    "DailyRunOrchestrator",
    "DailyRunResult",
    "daily_run_id",
]
