"""Deterministic trading-calendar scheduling decisions for WP-0031."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from .contracts import DailyRunStatus
from .daily_scheduler_contracts import DailyScheduleDecision, ScheduleAction, ScheduleTrigger
from .identity import operations_hash

SHANGHAI = ZoneInfo("Asia/Shanghai")
TRIGGER_TIMES = (time(8, 30), time(16, 35), time(16, 50), time(17, 10))


def evaluate_daily_schedule(
    *,
    open_dates: tuple[date, ...],
    evaluated_at: datetime,
    latest_run: DailyRunStatus | None,
) -> DailyScheduleDecision:
    if evaluated_at.tzinfo is None:
        raise ValueError("调度时间必须带时区")
    local = evaluated_at.astimezone(SHANGHAI)
    eligible = tuple(day for day in open_dates if day <= local.date())
    trigger = _trigger(local)
    target_date = _target_date(eligible, local, trigger)
    relevant = latest_run if latest_run and latest_run.target_date == target_date else None
    action, reason, blockers = _action(trigger, relevant, target_date)
    next_trigger = _next_trigger(open_dates, local)
    identity = {
        "evaluated_at": local,
        "target_date": target_date,
        "trigger": trigger,
        "action": action,
        "run_id": relevant.run_id if relevant else None,
        "reason_code": reason,
        "next_trigger_at": next_trigger,
        "blocker_codes": blockers,
        "broker_connection_attempts": 0,
        "broker_write_attempts": 0,
        "broker_actions_allowed": False,
    }
    digest = operations_hash(identity)
    return DailyScheduleDecision.model_validate(
        {
            **identity,
            "decision_id": "daily-schedule:" + digest.removeprefix("sha256:"),
            "content_hash": digest,
        }
    )


def _trigger(value: datetime) -> ScheduleTrigger:
    clock = value.timetz().replace(tzinfo=None)
    if time(8, 30) <= clock < time(9, 20):
        return "startup_0830"
    if time(16, 35) <= clock < time(16, 50):
        return "post_close_1635"
    if time(16, 50) <= clock < time(17, 10):
        return "provider_retry_1650"
    if time(17, 10) <= clock < time(17, 30):
        return "provider_retry_1710"
    if clock < time(16, 35) or clock >= time(17, 30):
        return "logon_recovery"
    return "outside_window"


def _target_date(
    eligible: tuple[date, ...],
    local: datetime,
    trigger: ScheduleTrigger,
) -> date | None:
    if not eligible:
        return None
    today_is_open = eligible[-1] == local.date()
    if trigger in ("post_close_1635", "provider_retry_1650", "provider_retry_1710"):
        return eligible[-1] if today_is_open else None
    if today_is_open and local.timetz().replace(tzinfo=None) < time(16, 35):
        return eligible[-2] if len(eligible) > 1 else None
    return eligible[-1]


def _action(
    trigger: ScheduleTrigger,
    status: DailyRunStatus | None,
    target_date: date | None,
) -> tuple[ScheduleAction, str, tuple[str, ...]]:
    if target_date is None:
        return "none", "no_eligible_trading_date", ()
    if status is None:
        return "run", "latest_trading_date_not_started", ()
    if status.state == "current":
        return "view", "daily_run_already_current", ()
    if status.state in ("waiting_provider", "recovery_required"):
        return "recover", f"{status.state}_resume_same_identity", ()
    if status.state in ("running", "lease_held"):
        return "view", "daily_run_already_active", ()
    if status.state in ("stale", "blocked"):
        return "view", "manual_attention_required", status.blocker_codes
    if trigger == "outside_window":
        return "none", "outside_bounded_window", ()
    return "recover", "incomplete_run_resume", ()


def _next_trigger(open_dates: tuple[date, ...], local: datetime) -> datetime | None:
    candidates: list[datetime] = []
    horizon = local.date() + timedelta(days=8)
    for day in open_dates:
        if day < local.date() or day > horizon:
            continue
        for trigger_time in TRIGGER_TIMES:
            value = datetime.combine(day, trigger_time, SHANGHAI)
            if value > local:
                candidates.append(value)
    return min(candidates, default=None)


__all__ = ["TRIGGER_TIMES", "evaluate_daily_schedule"]
