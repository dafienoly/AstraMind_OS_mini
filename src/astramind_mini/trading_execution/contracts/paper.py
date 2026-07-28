"""Strict broker-neutral contracts for offline Paper execution."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import Field, field_validator

from astramind_mini.contracts import ExecutionEvent, OrderPlan
from astramind_mini.contracts.base import (
    AwareDatetime,
    ContentHash,
    ContractModel,
    Identifier,
)


class PaperOrderState(StrEnum):
    PREPARED = "prepared"
    SUBMISSION_UNKNOWN = "submission_unknown"
    ACKNOWLEDGED = "acknowledged"
    PARTIALLY_FILLED = "partially_filled"
    CANCEL_PENDING = "cancel_pending"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


class PaperObservationKind(StrEnum):
    SUBMISSION_UNKNOWN = "submission_unknown"
    ACKNOWLEDGED = "acknowledged"
    PARTIAL_FILL = "partial_fill"
    FILLED = "filled"
    REJECTED = "rejected"
    CANCEL_REQUESTED = "cancel_requested"
    CANCELLED = "cancelled"
    RECOVERY_NOT_FOUND = "recovery_not_found"


class PaperPreflightDecision(ContractModel):
    decision_id: Identifier
    evidence_kind: Literal["synthetic_offline", "real_miniqmt"]
    evidence_ids: tuple[Identifier, ...] = ()
    account_mode_verified: bool
    reconciliation_matched: bool
    quote_fresh: bool
    trading_window_open: bool
    tradable: bool
    cash_sufficient: bool
    lot_valid: bool
    t_plus_one_valid: bool
    drawdown_allowed: bool
    mandate_approved: bool
    blocker_codes: tuple[Identifier, ...] = ()
    paper_write_authorized: Literal[False] = False
    created_at: AwareDatetime
    content_hash: ContentHash


class PaperOrderIntent(ContractModel):
    intent_id: Identifier
    order_plan: OrderPlan
    line_id: Identifier
    idempotency_key: Identifier
    instrument_id: Identifier
    side: Literal["buy", "sell"]
    quantity: int = Field(gt=0)
    limit_price: float = Field(gt=0)
    preflight_decision_id: Identifier
    broker_actions_allowed: Literal[False] = False
    created_at: AwareDatetime
    content_hash: ContentHash

    @field_validator("instrument_id")
    @classmethod
    def validate_instrument(cls, value: str) -> str:
        parts = value.split(".")
        if len(parts) != 2 or len(parts[0]) != 6 or not parts[0].isdigit():
            raise ValueError("Paper 第一版只接受六位 A 股证券代码")
        if parts[1] not in {"SH", "SZ", "BJ"}:
            raise ValueError("Paper 第一版只接受 SH、SZ 或 BJ 市场")
        return value

    @field_validator("quantity")
    @classmethod
    def validate_lot(cls, value: int) -> int:
        if value % 100:
            raise ValueError("Paper 第一版数量必须是 100 股整数手")
        return value


class PaperBrokerObservation(ContractModel):
    evidence_id: Identifier
    intent_id: Identifier
    idempotency_key: Identifier
    execution_event: ExecutionEvent
    kind: PaperObservationKind
    broker_sequence: int | None = Field(default=None, ge=0)
    cumulative_filled_quantity: int = Field(ge=0)
    average_fill_price: float | None = Field(default=None, gt=0)
    broker_order_fingerprint: ContentHash | None = None
    source: Literal["synthetic_offline", "broker_callback", "broker_query"]
    received_at: AwareDatetime
    content_hash: ContentHash


class PaperOrderProjection(ContractModel):
    projection_id: Identifier
    intent_id: Identifier
    idempotency_key: Identifier
    state: PaperOrderState
    requested_quantity: int = Field(gt=0)
    cumulative_filled_quantity: int = Field(ge=0)
    remaining_quantity: int = Field(ge=0)
    broker_order_fingerprint: ContentHash | None = None
    last_broker_sequence: int | None = Field(default=None, ge=0)
    evidence_count: int = Field(ge=0)
    recovery_required: bool
    retry_permitted: Literal[False] = False
    broker_actions_allowed: Literal[False] = False
    updated_at: AwareDatetime
    content_hash: ContentHash


__all__ = [
    "PaperBrokerObservation",
    "PaperObservationKind",
    "PaperOrderIntent",
    "PaperOrderProjection",
    "PaperOrderState",
    "PaperPreflightDecision",
]
