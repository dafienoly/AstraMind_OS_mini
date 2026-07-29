"""Strict status contracts for the resumable daily data pipeline."""

from __future__ import annotations

from datetime import date
from typing import Literal

from astramind_mini.contracts.base import (
    AwareDatetime,
    ContentHash,
    ContractModel,
    Identifier,
)

DailyPipelineState = Literal[
    "waiting_window",
    "waiting_provider",
    "running",
    "current",
    "stale",
    "blocked",
    "recovery_required",
    "no_session",
]


class DailyPipelineCheckpoint(ContractModel):
    run_id: Identifier
    step_id: Identifier
    artifact_identity: str | None = None
    completed_at: AwareDatetime
    content_hash: ContentHash


class DailyPipelineStatus(ContractModel):
    run_id: Identifier
    target_date: date
    base_snapshot_id: Identifier
    state: DailyPipelineState
    current_step: str | None = None
    attempt: int
    expected_l1_count: int
    expected_l2_count: int
    observed_l1_count: int = 0
    observed_l2_count: int = 0
    data_snapshot_id: Identifier | None = None
    rotation_snapshot_id: Identifier | None = None
    blocker_codes: tuple[str, ...] = ()
    recovery_action: str | None = None
    started_at: AwareDatetime
    updated_at: AwareDatetime
    completed_at: AwareDatetime | None = None
    broker_actions_allowed: Literal[False] = False
    content_hash: ContentHash


class DailyPipelineCommit(ContractModel):
    commit_id: Identifier
    run_id: Identifier
    target_date: date
    data_snapshot_id: Identifier
    rotation_snapshot_id: Identifier
    committed_at: AwareDatetime
    broker_actions_allowed: Literal[False] = False
    content_hash: ContentHash


__all__ = [
    "DailyPipelineCheckpoint",
    "DailyPipelineCommit",
    "DailyPipelineState",
    "DailyPipelineStatus",
]
