"""Strict local operations evidence without secret or broker payload fields."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import Field

from astramind_mini.contracts.base import (
    AwareDatetime,
    ContentHash,
    ContractModel,
    Identifier,
    Version,
)


class OperationsWindowDecision(ContractModel):
    decision_id: Identifier
    trading_date: date
    next_trading_date: date
    evaluated_at: AwareDatetime
    phase: Literal["waiting", "post_close", "pre_open", "outside_window"]
    status: Literal["waiting", "ready", "blocked", "stale"]
    task_ids: tuple[Identifier, ...]
    blocker_codes: tuple[str, ...] = ()
    recovery_action: str | None = None
    daily_budget_minutes: Literal[30] = 30
    paper_preflight_ready: Literal[False] = False
    broker_actions_allowed: Literal[False] = False
    policy_version: Version
    content_hash: ContentHash


class BackupFile(ContractModel):
    logical_name: Identifier
    kind: Literal["sqlite", "pointer"]
    relative_path: str
    size_bytes: int = Field(ge=0)
    content_hash: ContentHash


class BackupManifest(ContractModel):
    backup_id: Identifier
    reason: Literal["daily_close", "pre_migration", "pre_first_broker_write", "manual"]
    logical_date: date
    created_at: AwareDatetime
    status: Literal["complete", "partial"]
    files: tuple[BackupFile, ...]
    missing_sources: tuple[Identifier, ...] = ()
    configuration_fingerprint: ContentHash
    retention_policy_version: Literal["daily30-monthly12-v1"] = "daily30-monthly12-v1"
    paper_backup_ready: bool
    broker_actions_allowed: Literal[False] = False
    content_hash: ContentHash


class RecoveryDrillReport(ContractModel):
    report_id: Identifier
    backup_id: Identifier
    started_at: AwareDatetime
    completed_at: AwareDatetime
    status: Literal["healthy", "blocked"]
    verified_file_count: int = Field(ge=0)
    sqlite_integrity_count: int = Field(ge=0)
    shadow_event_count: int = Field(ge=0)
    blocker_codes: tuple[str, ...] = ()
    recovery_target_minutes: Literal[30] = 30
    paper_recovery_ready: bool
    broker_actions_allowed: Literal[False] = False
    content_hash: ContentHash


class OfflineGuardTaskResult(ContractModel):
    task_id: Identifier
    state: Literal["completed", "blocked", "skipped"]
    attempt: int = Field(ge=1)
    output_identity: Identifier | None = None
    blocker_codes: tuple[Identifier, ...] = ()
    recovery_action: str | None = None
    started_at: AwareDatetime
    completed_at: AwareDatetime
    broker_actions_allowed: Literal[False] = False
    content_hash: ContentHash


class OfflineGuardRun(ContractModel):
    run_id: Identifier
    logical_date: date
    owner_id: Identifier
    state: Literal["completed", "blocked"]
    task_results: tuple[OfflineGuardTaskResult, ...]
    blocker_codes: tuple[Identifier, ...] = ()
    started_at: AwareDatetime
    completed_at: AwareDatetime
    policy_version: Literal["offline-paper-guard-v1.0.0"] = "offline-paper-guard-v1.0.0"
    paper_dispatch_state: Literal["disabled"] = "disabled"
    broker_actions_allowed: Literal[False] = False
    content_hash: ContentHash


class OfflineFaultCaseResult(ContractModel):
    scenario: Literal[
        "stale_data",
        "foreign_open_order",
        "mandate_expired",
        "submission_unknown",
        "callback_out_of_order",
        "restart_after_checkpoint",
        "duplicate_instance",
        "sqlite_write_failure",
    ]
    status: Literal["passed", "failed"]
    observed_blocker_codes: tuple[Identifier, ...]
    duplicate_side_effect_count: int = Field(ge=0)
    recovery_mode: Literal["none", "resume_checkpoint", "query_only", "operator_action"]
    broker_actions_allowed: Literal[False] = False
    content_hash: ContentHash


class OfflineFaultDrillReport(ContractModel):
    report_id: Identifier
    logical_date: date
    started_at: AwareDatetime
    completed_at: AwareDatetime
    status: Literal["passed", "failed"]
    cases: tuple[OfflineFaultCaseResult, ...]
    blocker_codes: tuple[Identifier, ...] = ()
    broker_connection_attempts: Literal[0] = 0
    broker_write_attempts: Literal[0] = 0
    broker_actions_allowed: Literal[False] = False
    content_hash: ContentHash


__all__ = [
    "BackupFile",
    "BackupManifest",
    "OfflineFaultCaseResult",
    "OfflineFaultDrillReport",
    "OfflineGuardRun",
    "OfflineGuardTaskResult",
    "OperationsWindowDecision",
    "RecoveryDrillReport",
]
