"""Contracts for a recoverable continuous Paper runtime."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from astramind_mini.contracts.base import (
    AwareDatetime,
    ContentHash,
    ContractModel,
    Identifier,
)


class PaperLimitProposal(ContractModel):
    proposal_id: Identifier
    authorization_id: Identifier
    mandate_account_baseline_id: Identifier
    account_baseline_id: Identifier
    source_portfolio_target_id: Identifier
    instrument_id: Identifier
    side: Literal["buy"]
    quantity: int = Field(gt=0)
    indicative_best_ask: float = Field(gt=0)
    exact_limit_price: float = Field(gt=0)
    maximum_notional_cny: int = Field(gt=0)
    proposed_notional_cny: float = Field(gt=0)
    quote_market_time: AwareDatetime
    quote_received_at: AwareDatetime
    submission_window_end: AwareDatetime
    state: Literal["awaiting_user_approval"]
    broker_actions_allowed: Literal[False] = False
    content_hash: ContentHash

    @model_validator(mode="after")
    def validate_scope(self) -> PaperLimitProposal:
        if round(self.exact_limit_price, 2) != self.exact_limit_price:
            raise ValueError("A 股限价必须按0.01元精度")
        if self.proposed_notional_cny > self.maximum_notional_cny:
            raise ValueError("委托金额超过 Mandate 上限")
        if self.quote_market_time > self.quote_received_at:
            raise ValueError("行情市场时间不能晚于接收时间")
        return self


class PaperSubmissionApproval(ContractModel):
    approval_id: Identifier
    proposal_id: Identifier
    authorization_id: Identifier
    exact_limit_price: float = Field(gt=0)
    approved_at: AwareDatetime
    effective_to: AwareDatetime
    single_submission: Literal[True]
    cancel_this_order_only: Literal[True]
    broker_actions_allowed: Literal[True]
    content_hash: ContentHash

    @model_validator(mode="after")
    def validate_time(self) -> PaperSubmissionApproval:
        if self.effective_to <= self.approved_at:
            raise ValueError("首笔委托批准必须具有未来失效时间")
        if (self.effective_to - self.approved_at).total_seconds() > 180:
            raise ValueError("首笔委托批准有效期不得超过3分钟")
        return self


class PaperBrokerCommandResult(ContractModel):
    command_id: Identifier
    intent_id: Identifier
    action: Literal["query", "submit", "cancel"]
    outcome: Literal[
        "not_found",
        "existing",
        "accepted",
        "rejected",
        "cancel_requested",
        "unknown",
    ]
    broker_order_fingerprint: ContentHash | None
    broker_status_code: str | None
    cumulative_filled_quantity: int = Field(ge=0)
    average_fill_price: float | None = Field(default=None, ge=0)
    observed_at: AwareDatetime
    content_hash: ContentHash


class PaperOperationsSnapshot(ContractModel):
    as_of: AwareDatetime
    execution_mode: Literal["paper"]
    account_mode: Literal["simulation"]
    broker_connection: Literal["disconnected", "readonly", "connected"]
    canary_state: Literal[
        "not_authorized",
        "awaiting_final_limit_approval",
        "ready_to_submit",
        "working",
        "terminal",
        "blocked",
    ]
    standing_mandate_id: Identifier | None
    authorization_id: Identifier | None
    instrument_id: Identifier | None
    side: Literal["buy"] | None
    quantity: int | None = Field(default=None, gt=0)
    max_notional_cny: int | None = Field(default=None, gt=0)
    mandate_effective_from: AwareDatetime | None
    mandate_effective_to: AwareDatetime | None
    submission_window_start: AwareDatetime | None
    submission_window_end: AwareDatetime | None
    inherited_overlap: Literal["allowed"] | None
    account_baseline_state: Literal["missing", "readonly_ready", "blocked"]
    inherited_position_count: int = Field(ge=0)
    open_order_count: int = Field(ge=0)
    intent_count: int = Field(ge=0)
    observation_count: int = Field(ge=0)
    blocker_codes: tuple[Identifier, ...]
    next_action: str
    broker_actions_allowed: bool


__all__ = [
    "PaperBrokerCommandResult",
    "PaperLimitProposal",
    "PaperOperationsSnapshot",
    "PaperSubmissionApproval",
]
