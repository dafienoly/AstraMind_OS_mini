"""Deterministic Asia/Shanghai daily operations window decisions."""

from __future__ import annotations

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from .contracts import OperationsWindowDecision
from .identity import operations_hash

SHANGHAI = ZoneInfo("Asia/Shanghai")
POLICY_VERSION = "local-daily-operations-v1.0.0"
POST_CLOSE_TASKS = (
    "data_increment",
    "snapshot_publication",
    "decision_chain",
    "continuous_shadow_advance",
    "daily_close_backup",
)
PRE_OPEN_TASKS = (
    "backup_health_check",
    "shadow_replay_check",
    "paper_preflight_remains_blocked",
)


def evaluate_daily_window(
    *,
    trading_date: date,
    next_trading_date: date,
    evaluated_at: datetime,
    provider_complete: bool,
    pipeline_completed: bool,
    backup_ready: bool,
) -> OperationsWindowDecision:
    if evaluated_at.tzinfo is None:
        raise ValueError("本地运行决策时间必须带时区")
    local = evaluated_at.astimezone(SHANGHAI)
    post_start = datetime.combine(trading_date, time(16, 30), SHANGHAI)
    post_deadline = datetime.combine(trading_date, time(17, 0), SHANGHAI)
    pre_start = datetime.combine(next_trading_date, time(8, 30), SHANGHAI)
    pre_end = datetime.combine(next_trading_date, time(9, 20), SHANGHAI)

    phase = "waiting"
    status = "waiting"
    tasks: tuple[str, ...] = ()
    blockers: tuple[str, ...] = ()
    recovery: str | None = None
    if post_start <= local <= post_deadline:
        phase = "post_close"
        tasks = POST_CLOSE_TASKS
        status = "ready" if provider_complete else "blocked"
        if not provider_complete:
            blockers = ("provider_not_complete",)
            recovery = "等待提供方确认完成后使用相同输入身份重试"
    elif post_deadline < local < pre_start and not pipeline_completed:
        phase = "outside_window"
        status = "stale"
        blockers = ("daily_pipeline_budget_exceeded",)
        recovery = "停止无限重试，检查最后完成步骤并从幂等入口恢复"
    elif pre_start <= local <= pre_end:
        phase = "pre_open"
        tasks = PRE_OPEN_TASKS
        status = "ready" if backup_ready else "blocked"
        if not backup_ready:
            blockers = ("backup_or_recovery_not_ready",)
            recovery = "运行隔离恢复演练；Paper 保持阻断"
    elif local > pre_end:
        phase = "outside_window"

    identity = {
        "trading_date": trading_date,
        "next_trading_date": next_trading_date,
        "evaluated_at": evaluated_at,
        "phase": phase,
        "status": status,
        "task_ids": tasks,
        "blocker_codes": blockers,
        "recovery_action": recovery,
        "daily_budget_minutes": 30,
        "policy_version": POLICY_VERSION,
    }
    digest = operations_hash(identity)
    return OperationsWindowDecision.model_validate(
        {
            "decision_id": "operations-window:" + digest.removeprefix("sha256:"),
            "content_hash": digest,
            **identity,
        }
    )


__all__ = ["POLICY_VERSION", "evaluate_daily_window"]
