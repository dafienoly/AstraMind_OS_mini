"""Strict authorization evidence for the first MiniQMT Paper canary."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, field_validator, model_validator

from astramind_mini.contracts import StandingMandate
from astramind_mini.contracts.base import (
    AwareDatetime,
    ContentHash,
    ContractModel,
    Identifier,
)


class PaperCanaryAuthorization(ContractModel):
    authorization_id: Identifier
    standing_mandate: StandingMandate
    source_portfolio_target_id: Identifier
    source_shadow_order_plan_id: Identifier
    account_baseline_id: Identifier
    account_mode: Literal["simulation"]
    instrument_id: Identifier
    side: Literal["buy"]
    quantity: int = Field(gt=0)
    order_type: Literal["limit"]
    max_notional_cny: int = Field(gt=0)
    submission_window_start: AwareDatetime
    submission_window_end: AwareDatetime
    quote_max_age_seconds: Literal[3]
    one_order_only: Literal[True]
    unconfirmed_action: Literal["query_only_no_resubmit"]
    cancel_scope: Literal["this_canary_only"]
    inherited_overlap: Literal["allowed"]
    final_numeric_limit_approval_required: Literal[True]
    state: Literal["awaiting_final_limit_approval"]
    broker_actions_allowed: Literal[False] = False
    approved_at: AwareDatetime
    content_hash: ContentHash

    @field_validator("instrument_id")
    @classmethod
    def validate_main_board_instrument(cls, value: str) -> str:
        if not value.endswith(".SH") or value.startswith("688") or len(value) != 9:
            raise ValueError("首笔 100 股金丝雀只允许沪市主板 A 股")
        if not value[:6].isdigit():
            raise ValueError("证券代码必须是六位数字加 .SH")
        return value

    @field_validator("quantity")
    @classmethod
    def validate_board_lot(cls, value: int) -> int:
        if value % 100:
            raise ValueError("买入数量必须是 100 股整数倍")
        return value

    @model_validator(mode="after")
    def validate_windows(self) -> PaperCanaryAuthorization:
        mandate = self.standing_mandate
        if mandate.effective_to is None:
            raise ValueError("金丝雀 StandingMandate 必须有明确失效时间")
        if not (
            mandate.effective_from
            <= self.submission_window_start
            < self.submission_window_end
            <= mandate.effective_to
        ):
            raise ValueError("提交窗口必须完整位于 StandingMandate 有效期内")
        return self


__all__ = ["PaperCanaryAuthorization"]
