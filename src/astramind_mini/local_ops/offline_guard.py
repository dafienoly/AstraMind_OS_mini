"""Resumable offline daily guard that can never dispatch a broker action."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from .contracts import OfflineGuardRun, OfflineGuardTaskResult
from .guard_store import OfflineGuardStore
from .identity import operations_hash

POLICY_VERSION = "offline-paper-guard-v1.0.0"
LEASE_NAME = "offline-paper-daily-guard"
TASK_IDS = (
    "backup_recovery",
    "data_snapshot",
    "feature_snapshot",
    "prediction_batch",
    "portfolio_target",
    "order_plan",
    "risk_mandate_preview",
    "paper_dispatch_disabled",
)


class OfflineGuardInterrupted(RuntimeError):
    """Synthetic process interruption after a durable checkpoint."""


@dataclass(frozen=True)
class OfflineGuardInputs:
    backup_id: str | None
    recovery_report_id: str | None
    data_snapshot_id: str | None
    feature_snapshot_id: str | None
    prediction_batch_id: str | None
    portfolio_target_id: str | None
    order_plan_id: str | None
    mandate_preview_id: str | None
    data_fresh: bool = True
    foreign_open_order_count: int = 0
    mandate_active: bool = True
    submission_unknown: bool = False
    callback_order_valid: bool = True
    storage_writable: bool = True

    def identity(self) -> dict[str, object]:
        return {
            "backup_id": self.backup_id,
            "recovery_report_id": self.recovery_report_id,
            "data_snapshot_id": self.data_snapshot_id,
            "feature_snapshot_id": self.feature_snapshot_id,
            "prediction_batch_id": self.prediction_batch_id,
            "portfolio_target_id": self.portfolio_target_id,
            "order_plan_id": self.order_plan_id,
            "mandate_preview_id": self.mandate_preview_id,
            "data_fresh": self.data_fresh,
            "foreign_open_order_count": self.foreign_open_order_count,
            "mandate_active": self.mandate_active,
            "submission_unknown": self.submission_unknown,
            "callback_order_valid": self.callback_order_valid,
            "storage_writable": self.storage_writable,
        }


class OfflineDailyGuard:
    def __init__(self, store: OfflineGuardStore) -> None:
        self._store = store

    def run(
        self,
        *,
        logical_date: date,
        owner_id: str,
        inputs: OfflineGuardInputs,
        started_at: datetime,
        interrupt_after_task: str | None = None,
    ) -> OfflineGuardRun:
        if started_at.tzinfo is None:
            raise ValueError("离线守护启动时间必须带时区")
        run_id = _run_id(logical_date, inputs)
        existing = self._store.run(run_id)
        if existing is not None:
            return existing
        lease_expiry = started_at + timedelta(seconds=30)
        self._store.acquire_lease(
            lease_name=LEASE_NAME,
            owner_id=owner_id,
            heartbeat_at=started_at,
            expires_at=lease_expiry,
        )
        results: list[OfflineGuardTaskResult] = []
        blocked = False
        try:
            for index, task_id in enumerate(TASK_IDS):
                checkpoint = self._store.task_result(run_id=run_id, task_id=task_id)
                if checkpoint is not None:
                    results.append(checkpoint)
                    blocked = blocked or checkpoint.state != "completed"
                    continue
                task_time = started_at + timedelta(milliseconds=index + 1)
                result = (
                    _skipped(task_id, task_time)
                    if blocked
                    else _evaluate(task_id=task_id, inputs=inputs, at=task_time)
                )
                self._store.publish_task(run_id=run_id, value=result)
                results.append(result)
                blocked = blocked or result.state != "completed"
                self._store.heartbeat(
                    lease_name=LEASE_NAME,
                    owner_id=owner_id,
                    heartbeat_at=task_time,
                    expires_at=task_time + timedelta(seconds=30),
                )
                if interrupt_after_task == task_id:
                    raise OfflineGuardInterrupted(f"在 {task_id} 检查点后模拟中断")
            completed_at = started_at + timedelta(milliseconds=len(TASK_IDS) + 1)
            blockers = tuple(
                sorted(
                    {
                        code
                        for result in results
                        for code in result.blocker_codes
                        if result.state == "blocked"
                    }
                )
            )
            run = _guard_run(
                run_id=run_id,
                logical_date=logical_date,
                owner_id=owner_id,
                state="blocked" if blockers else "completed",
                results=tuple(results),
                blockers=blockers,
                started_at=started_at,
                completed_at=completed_at,
            )
            self._store.publish_run(run)
            return run
        finally:
            self._store.release_lease(lease_name=LEASE_NAME, owner_id=owner_id)


def _evaluate(*, task_id: str, inputs: OfflineGuardInputs, at: datetime) -> OfflineGuardTaskResult:
    output: str | None = None
    blockers: tuple[str, ...] = ()
    recovery: str | None = None
    if task_id == "backup_recovery":
        output = inputs.recovery_report_id
        if not inputs.storage_writable:
            blockers = ("control_store_unwritable",)
            recovery = "修复本地控制库写入后从最后检查点恢复"
        elif not inputs.backup_id or not inputs.recovery_report_id:
            blockers = ("backup_or_recovery_not_ready",)
            recovery = "完成仓库外备份及隔离恢复演练"
    elif task_id == "data_snapshot":
        output = inputs.data_snapshot_id
        if not inputs.data_fresh:
            blockers = ("data_stale",)
            recovery = "更新到最近完成交易日并发布不可变 DataSnapshot"
        elif not output:
            blockers = ("data_snapshot_missing",)
            recovery = "先发布准确 DataSnapshot"
    elif task_id == "feature_snapshot":
        output = inputs.feature_snapshot_id
        blockers, recovery = _required(output, "feature_snapshot_missing")
    elif task_id == "prediction_batch":
        output = inputs.prediction_batch_id
        blockers, recovery = _required(output, "prediction_batch_missing")
    elif task_id == "portfolio_target":
        output = inputs.portfolio_target_id
        blockers, recovery = _required(output, "portfolio_target_missing")
    elif task_id == "order_plan":
        output = inputs.order_plan_id
        blockers, recovery = _required(output, "order_plan_missing")
    elif task_id == "risk_mandate_preview":
        output = inputs.mandate_preview_id
        if inputs.submission_unknown:
            blockers = ("submission_unknown_query_only",)
            recovery = "只按幂等身份查询券商事实，禁止重提"
        elif inputs.foreign_open_order_count:
            blockers = ("foreign_open_order_present",)
            recovery = "人工核对并处置非本系统未完成委托"
        elif not inputs.callback_order_valid:
            blockers = ("callback_sequence_invalid",)
            recovery = "重放不可变事件并完成只读对账"
        elif not inputs.mandate_active:
            blockers = ("standing_mandate_expired",)
            recovery = "保持 Paper 禁用，等待新版准确 Mandate"
        elif not output:
            blockers = ("mandate_preview_missing",)
            recovery = "生成不激活的持续 Paper Mandate 预览"
    elif task_id == "paper_dispatch_disabled":
        output = "paper-dispatch:disabled"
    else:
        raise ValueError(f"未知离线守护任务：{task_id}")
    return _task_result(
        task_id=task_id,
        state="blocked" if blockers else "completed",
        output=output,
        blockers=blockers,
        recovery=recovery,
        at=at,
    )


def _required(output: str | None, blocker: str) -> tuple[tuple[str, ...], str | None]:
    if output:
        return (), None
    return (blocker,), "从同一不可变上游身份恢复该步骤"


def _skipped(task_id: str, at: datetime) -> OfflineGuardTaskResult:
    return _task_result(
        task_id=task_id,
        state="skipped",
        output=None,
        blockers=("upstream_blocked",),
        recovery="解决首个阻断后以相同输入重新运行",
        at=at,
    )


def _task_result(
    *,
    task_id: str,
    state: str,
    output: str | None,
    blockers: tuple[str, ...],
    recovery: str | None,
    at: datetime,
) -> OfflineGuardTaskResult:
    identity = {
        "task_id": task_id,
        "state": state,
        "attempt": 1,
        "output_identity": output,
        "blocker_codes": blockers,
        "recovery_action": recovery,
        "started_at": at,
        "completed_at": at,
        "broker_actions_allowed": False,
    }
    return OfflineGuardTaskResult.model_validate(
        {**identity, "content_hash": operations_hash(identity)}
    )


def _guard_run(
    *,
    run_id: str,
    logical_date: date,
    owner_id: str,
    state: str,
    results: tuple[OfflineGuardTaskResult, ...],
    blockers: tuple[str, ...],
    started_at: datetime,
    completed_at: datetime,
) -> OfflineGuardRun:
    identity = {
        "run_id": run_id,
        "logical_date": logical_date,
        "owner_id": owner_id,
        "state": state,
        "task_results": results,
        "blocker_codes": blockers,
        "started_at": started_at,
        "completed_at": completed_at,
        "policy_version": POLICY_VERSION,
        "paper_dispatch_state": "disabled",
        "broker_actions_allowed": False,
    }
    return OfflineGuardRun.model_validate({**identity, "content_hash": operations_hash(identity)})


def _run_id(logical_date: date, inputs: OfflineGuardInputs) -> str:
    digest = operations_hash(
        {
            "logical_date": logical_date,
            "inputs": inputs.identity(),
            "policy_version": POLICY_VERSION,
        }
    )
    return "offline-guard-run:" + digest.removeprefix("sha256:")


__all__ = [
    "LEASE_NAME",
    "POLICY_VERSION",
    "TASK_IDS",
    "OfflineDailyGuard",
    "OfflineGuardInputs",
    "OfflineGuardInterrupted",
]
