"""Frozen local scheduling evidence for Daily Ops 1.0."""

from __future__ import annotations

from datetime import date
from typing import Literal

from astramind_mini.contracts.base import (
    AwareDatetime,
    ContentHash,
    ContractModel,
    Identifier,
)

ScheduleTrigger = Literal[
    "post_close_1635",
    "provider_retry_1650",
    "provider_retry_1710",
    "finalize_2010",
    "startup_0830",
    "logon_recovery",
    "outside_window",
]
ScheduleAction = Literal["run", "recover", "view", "none"]


class DailyScheduleDecision(ContractModel):
    decision_id: Identifier
    evaluated_at: AwareDatetime
    target_date: date | None = None
    trigger: ScheduleTrigger
    action: ScheduleAction
    run_id: Identifier | None = None
    reason_code: Identifier
    next_trigger_at: AwareDatetime | None = None
    blocker_codes: tuple[Identifier, ...] = ()
    broker_connection_attempts: Literal[0] = 0
    broker_write_attempts: Literal[0] = 0
    broker_actions_allowed: Literal[False] = False
    content_hash: ContentHash


class DailyScheduleDeployment(ContractModel):
    deployment_id: Literal["daily-ops-scheduler"] = "daily-ops-scheduler"
    state: Literal["not_installed", "installed", "paused", "error"]
    task_name: Identifier
    trigger_labels: tuple[str, ...]
    next_run_at: AwareDatetime | None = None
    last_result: str | None = None
    updated_at: AwareDatetime
    broker_actions_allowed: Literal[False] = False
    content_hash: ContentHash


class DailyRunRequest(ContractModel):
    request_id: Identifier
    request_key: Identifier
    action: Literal["run", "recover", "retry_provider"]
    target_date: date | None = None
    run_id: Identifier | None = None
    state: Literal["pending", "claimed", "completed", "superseded"]
    origin: Literal["local_ui"] = "local_ui"
    created_at: AwareDatetime
    updated_at: AwareDatetime
    broker_actions_allowed: Literal[False] = False
    content_hash: ContentHash


__all__ = [
    "DailyRunRequest",
    "DailyScheduleDecision",
    "DailyScheduleDeployment",
    "ScheduleAction",
    "ScheduleTrigger",
]
