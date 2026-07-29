"""Shared read projection for the System and Today Daily Ops views."""

from __future__ import annotations

from datetime import date, datetime, time
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict

from astramind_mini.data.adapters import DailyPipelineStore
from astramind_mini.data.contracts import DailyPipelineStatus

from .contracts import DailyDecisionStatus, DailyRunStatus
from .daily_decision_store import DailyDecisionStore
from .daily_run_store import DailyRunStore
from .daily_schedule_deployment import TASK_NAME, TRIGGER_LABELS
from .daily_scheduler_contracts import DailyRunRequest, DailyScheduleDeployment
from .daily_scheduler_store import DailySchedulerStore
from .identity import operations_hash

SHANGHAI = ZoneInfo("Asia/Shanghai")


class DailyAttentionItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    code: str
    severity: Literal["notice", "warning", "blocked"]
    title: str
    detail: str
    action: Literal["view", "run", "recover", "retry_provider", "install_scheduler"]


class DailyOperationsProjection(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    as_of: datetime
    pipeline: DailyPipelineStatus | None
    decision: DailyDecisionStatus | None
    latest_run: DailyRunStatus | None
    recent_runs: tuple[DailyRunStatus, ...]
    schedule: DailyScheduleDeployment
    pending_request: DailyRunRequest | None
    attention: tuple[DailyAttentionItem, ...]
    broker_actions_allowed: Literal[False] = False


class DailyOperationsReader:
    def __init__(
        self,
        *,
        control_database: Path,
        local_ops_database: Path,
        data_root: Path,
        decision_root: Path = Path("var/research/daily-decision"),
        run_root: Path = Path("var/operations/daily-runs"),
    ) -> None:
        self._pipeline = DailyPipelineStore(control_database, data_root)
        self._decision = DailyDecisionStore(local_ops_database, decision_root)
        self._runs = DailyRunStore(local_ops_database, run_root)
        self._scheduler = DailySchedulerStore(local_ops_database)

    def current(self, as_of: datetime | None = None) -> DailyOperationsProjection:
        observed_at = as_of or datetime.now(SHANGHAI)
        if observed_at.tzinfo is None:
            raise ValueError("日常运行投影时间必须带时区")
        pipeline = self._pipeline.latest_status()
        decision = self._decision.latest_status()
        recent_runs = self._runs.recent_statuses()
        latest_run = recent_runs[0] if recent_runs else None
        schedule = self._scheduler.deployment() or _not_installed(observed_at)
        pending = self._scheduler.pending_request()
        return DailyOperationsProjection(
            as_of=observed_at,
            pipeline=pipeline,
            decision=decision,
            latest_run=latest_run,
            recent_runs=recent_runs,
            schedule=schedule,
            pending_request=pending,
            attention=_attention(observed_at, latest_run, schedule, pending),
        )


def _not_installed(as_of: datetime) -> DailyScheduleDeployment:
    identity = {
        "deployment_id": "daily-ops-scheduler",
        "state": "not_installed",
        "task_name": TASK_NAME,
        "trigger_labels": TRIGGER_LABELS,
        "next_run_at": None,
        "last_result": None,
        "updated_at": as_of,
        "broker_actions_allowed": False,
    }
    return DailyScheduleDeployment.model_validate(
        {**identity, "content_hash": operations_hash(identity)}
    )


def _attention(
    as_of: datetime,
    latest: DailyRunStatus | None,
    schedule: DailyScheduleDeployment,
    pending: DailyRunRequest | None,
) -> tuple[DailyAttentionItem, ...]:
    items: list[DailyAttentionItem] = []
    if schedule.state != "installed":
        items.append(
            DailyAttentionItem(
                code="daily_schedule_not_installed",
                severity="warning",
                title="日度计划任务尚未安装",
                detail="确认任务名称、四个时间点、仓库目录和环境文件来源后安装。",
                action="install_scheduler",
            )
        )
    if pending:
        items.append(
            DailyAttentionItem(
                code="daily_run_request_pending",
                severity="notice",
                title="本地运行请求已登记",
                detail="计划任务将在下一次触发时认领；重复点击不会创建第二个请求。",
                action="view",
            )
        )
        return tuple(items)
    if latest is None:
        items.append(
            DailyAttentionItem(
                code="daily_run_not_started",
                severity="notice",
                title="尚无统一日常运行记录",
                detail="可登记一次运行请求，实际执行仍由本地调度入口接管。",
                action="run",
            )
        )
    elif latest.state in ("recovery_required", "stale", "blocked"):
        items.append(
            DailyAttentionItem(
                code=f"daily_run_{latest.state}",
                severity="blocked" if latest.state == "blocked" else "warning",
                title="日常运行需要恢复",
                detail=latest.recovery_action or "查看阻塞证据后恢复同一运行。",
                action="recover",
            )
        )
    elif latest.state == "waiting_provider" and _provider_window_exhausted(
        as_of, latest.target_date
    ):
        items.append(
            DailyAttentionItem(
                code="daily_provider_window_exhausted",
                severity="warning",
                title="提供方补跑窗口已结束",
                detail=latest.recovery_action or "保留同一运行身份，待提供方数据完整后重试。",
                action="retry_provider",
            )
        )
    return tuple(items)


def _provider_window_exhausted(as_of: datetime, target_date: date) -> bool:
    local = as_of.astimezone(SHANGHAI)
    return target_date < local.date() or (
        target_date == local.date() and local.time() >= time(17, 10)
    )


__all__ = [
    "DailyAttentionItem",
    "DailyOperationsProjection",
    "DailyOperationsReader",
]
