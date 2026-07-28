"""Immutable checkpoints and terminal evidence for a continuous Shadow cycle."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import Field

from astramind_mini.contracts.base import (
    AwareDatetime,
    ContentHash,
    ContractModel,
    Identifier,
)

ShadowCycleStatus = Literal[
    "active",
    "exit_waiting",
    "completed",
    "completed_no_entry",
    "blocked",
]


class ShadowCycleCheckpoint(ContractModel):
    checkpoint_id: Identifier
    cycle_id: Identifier
    data_snapshot_id: Identifier
    trading_date: date
    phase: Literal["entry", "valuation", "exit"]
    status: ShadowCycleStatus
    state_id: Identifier
    sessions_elapsed: int = Field(ge=1)
    entry_order_plan_id: Identifier
    exit_order_plan_id: Identifier | None = None
    event_count: int = Field(ge=0)
    market_evidence_hash: ContentHash
    blocker_codes: tuple[str, ...] = ()
    recorded_at: AwareDatetime
    broker_actions_allowed: Literal[False] = False
    content_hash: ContentHash


class ShadowCycleResult(ContractModel):
    result_id: Identifier
    cycle_id: Identifier
    status: Literal["completed", "completed_no_entry"]
    initial_state_id: Identifier
    terminal_state_id: Identifier
    entry_date: date
    exit_date: date | None = None
    sessions_elapsed: int = Field(ge=1)
    initial_equity_cny: float = Field(gt=0)
    terminal_equity_cny: float = Field(ge=0)
    total_return: float
    realized_profit_cny: float
    maximum_drawdown: float = Field(ge=0, le=1)
    checkpoint_count: int = Field(ge=1)
    execution_event_count: int = Field(ge=0)
    completed_at: AwareDatetime
    broker_actions_allowed: Literal[False] = False
    content_hash: ContentHash


__all__ = [
    "ShadowCycleCheckpoint",
    "ShadowCycleResult",
    "ShadowCycleStatus",
]
