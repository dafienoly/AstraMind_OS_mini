"""Pure Paper limit proposal and approval checks."""

from __future__ import annotations

from datetime import datetime

from ..contracts.paper_canary import PaperCanaryAuthorization
from ..contracts.paper_continuous import PaperLimitProposal, PaperSubmissionApproval
from .reconciliation import canonical_hash


def build_paper_limit_proposal(
    *,
    authorization: PaperCanaryAuthorization,
    account_baseline_id: str | None = None,
    best_ask: float,
    quote_market_time: datetime,
    quote_received_at: datetime,
) -> PaperLimitProposal:
    if not (
        authorization.submission_window_start
        <= quote_received_at
        <= authorization.submission_window_end
    ):
        raise ValueError("当前不在已批准的 Paper 提交窗口")
    if (quote_received_at - quote_market_time).total_seconds() > 3:
        raise ValueError("MiniQMT L1 行情超过3秒")
    limit_price = round(best_ask + 1e-9, 2)
    notional = round(limit_price * authorization.quantity, 2)
    payload = {
        "authorization_id": authorization.authorization_id,
        "mandate_account_baseline_id": authorization.account_baseline_id,
        "account_baseline_id": account_baseline_id or authorization.account_baseline_id,
        "source_portfolio_target_id": authorization.source_portfolio_target_id,
        "instrument_id": authorization.instrument_id,
        "side": authorization.side,
        "quantity": authorization.quantity,
        "indicative_best_ask": best_ask,
        "exact_limit_price": limit_price,
        "maximum_notional_cny": authorization.max_notional_cny,
        "proposed_notional_cny": notional,
        "quote_market_time": quote_market_time,
        "quote_received_at": quote_received_at,
        "submission_window_end": authorization.submission_window_end,
        "state": "awaiting_user_approval",
    }
    digest = canonical_hash(payload)
    return PaperLimitProposal.model_validate(
        {
            "proposal_id": "paper-limit-proposal:" + digest.removeprefix("sha256:"),
            "content_hash": digest,
            **payload,
        }
    )


def validate_submission_approval(
    *,
    proposal: PaperLimitProposal,
    approval: PaperSubmissionApproval,
    authorization: PaperCanaryAuthorization,
    fresh_best_ask: float,
    quote_market_time: datetime,
    now: datetime,
) -> None:
    if approval.proposal_id != proposal.proposal_id:
        raise ValueError("最终批准未绑定准确限价提案")
    if approval.authorization_id != authorization.authorization_id:
        raise ValueError("最终批准未绑定准确 StandingMandate")
    if approval.exact_limit_price != proposal.exact_limit_price:
        raise ValueError("最终批准的数值限价与提案不一致")
    if not authorization.submission_window_start <= now <= authorization.submission_window_end:
        raise ValueError("已批准提交窗口已经关闭")
    if now > approval.effective_to:
        raise ValueError("首笔委托批准已经失效")
    if (now - quote_market_time).total_seconds() > 3:
        raise ValueError("提交前 MiniQMT L1 行情超过3秒")
    if fresh_best_ask > approval.exact_limit_price:
        raise ValueError("最新卖一高于已批准限价，禁止追价")


__all__ = ["build_paper_limit_proposal", "validate_submission_approval"]
