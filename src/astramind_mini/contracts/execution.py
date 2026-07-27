"""Trading Execution-owned public identity contracts."""

from enum import StrEnum

from pydantic import Field

from .base import AwareDatetime, ContentHash, ContractModel, Identifier, Version
from .portfolio import Sleeve


class ExecutionMode(StrEnum):
    SHADOW = "shadow"
    PAPER = "paper"
    LIVE = "live"


class StandingMandate(ContractModel):
    standing_mandate_id: Identifier
    mandate_version: Version
    sleeve: Sleeve
    effective_from: AwareDatetime
    effective_to: AwareDatetime | None = None
    policy_hash: ContentHash


class OrderPlan(ContractModel):
    order_plan_id: Identifier
    portfolio_target_id: Identifier
    standing_mandate_id: Identifier | None = None
    execution_mode: ExecutionMode
    created_at: AwareDatetime
    content_hash: ContentHash


class ExecutionEvent(ContractModel):
    execution_event_id: Identifier
    order_plan_id: Identifier
    execution_mode: ExecutionMode
    event_type: Identifier
    sequence: int = Field(ge=0)
    occurred_at: AwareDatetime
    content_hash: ContentHash


__all__ = ["ExecutionEvent", "ExecutionMode", "OrderPlan", "StandingMandate"]
