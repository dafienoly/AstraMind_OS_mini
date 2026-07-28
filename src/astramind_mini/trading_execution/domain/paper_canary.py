"""Pure construction and validation of the first Paper canary authorization."""

from __future__ import annotations

from datetime import datetime

from astramind_mini.contracts import StandingMandate
from astramind_mini.contracts.portfolio import Sleeve

from ..contracts.paper_canary import PaperCanaryAuthorization
from .reconciliation import canonical_hash


def build_paper_canary_authorization(
    *,
    source_portfolio_target_id: str,
    source_shadow_order_plan_id: str,
    account_baseline_id: str,
    instrument_id: str,
    quantity: int,
    max_notional_cny: int,
    mandate_start: datetime,
    mandate_end: datetime,
    submission_start: datetime,
    submission_end: datetime,
    approved_at: datetime,
) -> PaperCanaryAuthorization:
    if max_notional_cny > 50_000:
        raise ValueError("首笔 Paper 金丝雀不得超过已批准的 50,000 元上限")
    policy = {
        "source_portfolio_target_id": source_portfolio_target_id,
        "source_shadow_order_plan_id": source_shadow_order_plan_id,
        "account_baseline_id": account_baseline_id,
        "account_mode": "simulation",
        "instrument_id": instrument_id,
        "side": "buy",
        "quantity": quantity,
        "order_type": "limit",
        "max_notional_cny": max_notional_cny,
        "submission_window_start": submission_start,
        "submission_window_end": submission_end,
        "quote_max_age_seconds": 3,
        "one_order_only": True,
        "unconfirmed_action": "query_only_no_resubmit",
        "cancel_scope": "this_canary_only",
        "inherited_overlap": "allowed",
        "final_numeric_limit_approval_required": True,
    }
    policy_hash = canonical_hash(policy)
    mandate = StandingMandate(
        standing_mandate_id="standing-mandate:" + policy_hash.removeprefix("sha256:"),
        mandate_version="paper-canary-v1",
        sleeve=Sleeve.TACTICAL,
        effective_from=mandate_start,
        effective_to=mandate_end,
        policy_hash=policy_hash,
    )
    payload = {
        "standing_mandate": mandate,
        **policy,
        "state": "awaiting_final_limit_approval",
        "approved_at": approved_at,
    }
    content_hash = canonical_hash(payload)
    return PaperCanaryAuthorization.model_validate(
        {
            "authorization_id": "paper-canary-authorization:"
            + content_hash.removeprefix("sha256:"),
            "content_hash": content_hash,
            **payload,
        }
    )


__all__ = ["build_paper_canary_authorization"]
