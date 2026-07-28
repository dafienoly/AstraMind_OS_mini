"""Strict contracts for reconciliation disposition and continuous Shadow."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import Field

from astramind_mini.contracts import OrderPlan
from astramind_mini.contracts.base import (
    AwareDatetime,
    ContentHash,
    ContractModel,
    Identifier,
    Version,
)

DrawdownLevel = Literal["normal", "warning", "freeze_new", "liquidation_proposal"]


class ReconciliationDisposition(ContractModel):
    disposition_id: Identifier
    account_snapshot_id: Identifier
    reconciliation_report_id: Identifier
    local_projection_id: Identifier
    resolution_kind: Literal["isolate_broker_simulation_state"]
    local_shadow_authority: Literal["synthetic_shadow_ledger"]
    resolved_blocker_codes: tuple[str, ...]
    local_shadow_allowed: Literal[True] = True
    broker_actions_allowed: Literal[False] = False
    policy_version: Version
    created_at: AwareDatetime
    content_hash: ContentHash


class ShadowStatePosition(ContractModel):
    instrument_id: Identifier
    quantity: int = Field(ge=0)
    available_quantity: int = Field(ge=0)
    average_cost: float = Field(ge=0)


class ContinuousShadowState(ContractModel):
    state_id: Identifier
    disposition_id: Identifier
    trading_date: date
    as_of: AwareDatetime
    cash_cny: float = Field(ge=0)
    positions: tuple[ShadowStatePosition, ...] = ()
    realized_profit_cny: float = 0
    equity_cny: float = Field(ge=0)
    sleeve_peak_equity_cny: float = Field(gt=0)
    account_equity_cny: float = Field(ge=0)
    account_peak_equity_cny: float = Field(gt=0)
    content_hash: ContentHash


class DrawdownDecision(ContractModel):
    decision_id: Identifier
    state_id: Identifier
    sleeve_drawdown: float = Field(ge=0, le=1)
    account_drawdown: float = Field(ge=0, le=1)
    effective_drawdown: float = Field(ge=0, le=1)
    level: DrawdownLevel
    expanding_risk_allowed: bool
    new_positions_allowed: bool
    all_buys_allowed: bool
    liquidation_proposal_required: bool
    automatic_liquidation_allowed: Literal[False] = False
    created_at: AwareDatetime
    content_hash: ContentHash


class ShadowPlanLine(ContractModel):
    instrument_id: Identifier
    side: Literal["buy", "sell"]
    requested_quantity: int = Field(gt=0)
    executable_quantity: int = Field(ge=0)
    reference_price: float = Field(gt=0)
    earliest_execution_date: date
    blocker_codes: tuple[str, ...] = ()
    execution_preconditions: tuple[str, ...] = (
        "fresh_quote",
        "tradable",
        "price_limit",
        "trading_window",
    )


class ContinuousShadowOrderPlan(ContractModel):
    order_plan: OrderPlan
    state_id: Identifier
    drawdown_decision_id: Identifier
    status: Literal["ready", "blocked", "no_action"]
    lines: tuple[ShadowPlanLine, ...]
    broker_actions_allowed: Literal[False] = False
    content_hash: ContentHash


class ContinuousShadowCycle(ContractModel):
    cycle_id: Identifier
    promotion_decision_id: Identifier
    data_snapshot_id: Identifier
    feature_snapshot_id: Identifier
    prediction_batch_id: Identifier
    portfolio_target_id: Identifier
    order_plan_id: Identifier
    signal_date: date
    nominal_execution_date: date
    scheduled_execution_date: date
    status: Literal["waiting_next_open", "no_action", "blocked"]
    warning_codes: tuple[str, ...] = ()
    broker_actions_allowed: Literal[False] = False
    created_at: AwareDatetime
    content_hash: ContentHash


__all__ = [
    "ContinuousShadowCycle",
    "ContinuousShadowOrderPlan",
    "ContinuousShadowState",
    "DrawdownDecision",
    "DrawdownLevel",
    "ReconciliationDisposition",
    "ShadowPlanLine",
    "ShadowStatePosition",
]
