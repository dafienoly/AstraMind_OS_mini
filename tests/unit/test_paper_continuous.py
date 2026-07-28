from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from astramind_mini.trading_execution.contracts.paper_canary import (
    PaperCanaryAuthorization,
)
from astramind_mini.trading_execution.contracts.paper_continuous import (
    PaperLimitProposal,
    PaperSubmissionApproval,
)
from astramind_mini.trading_execution.domain import (
    build_paper_canary_authorization,
    build_paper_limit_proposal,
    canonical_hash,
    validate_submission_approval,
)

SHANGHAI = timezone(timedelta(hours=8))
WINDOW_START = datetime(2026, 7, 29, 9, 35, tzinfo=SHANGHAI)


def _authorization() -> PaperCanaryAuthorization:
    return build_paper_canary_authorization(
        source_portfolio_target_id="portfolio-target:approved",
        source_shadow_order_plan_id="order-plan:shadow",
        account_baseline_id="paper-account-baseline:readonly",
        instrument_id="605208.SH",
        quantity=100,
        max_notional_cny=50_000,
        mandate_start=datetime(2026, 7, 29, 9, 30, tzinfo=SHANGHAI),
        mandate_end=datetime(2026, 7, 29, 10, 0, tzinfo=SHANGHAI),
        submission_start=WINDOW_START,
        submission_end=datetime(2026, 7, 29, 9, 45, tzinfo=SHANGHAI),
        approved_at=datetime(2026, 7, 28, 12, 30, tzinfo=SHANGHAI),
    )


def _proposal() -> PaperLimitProposal:
    received = WINDOW_START + timedelta(seconds=1)
    return build_paper_limit_proposal(
        authorization=_authorization(),
        best_ask=12.34,
        quote_market_time=received - timedelta(seconds=1),
        quote_received_at=received,
    )


def _approval() -> PaperSubmissionApproval:
    proposal = _proposal()
    payload = {
        "proposal_id": proposal.proposal_id,
        "authorization_id": proposal.authorization_id,
        "exact_limit_price": proposal.exact_limit_price,
        "approved_at": WINDOW_START + timedelta(seconds=2),
        "effective_to": WINDOW_START + timedelta(minutes=2),
        "single_submission": True,
        "cancel_this_order_only": True,
        "broker_actions_allowed": True,
    }
    digest = canonical_hash(payload)
    return PaperSubmissionApproval.model_validate(
        {
            "approval_id": "paper-submission-approval:" + digest[7:],
            "content_hash": digest,
            **payload,
        }
    )


def test_limit_proposal_is_exact_bounded_and_non_submittable() -> None:
    proposal = _proposal()
    assert proposal.exact_limit_price == 12.34
    assert proposal.proposed_notional_cny == 1_234
    assert proposal.broker_actions_allowed is False
    with pytest.raises(ValidationError):
        proposal.exact_limit_price = 12.35


def test_stale_or_out_of_window_quote_fails_closed() -> None:
    with pytest.raises(ValueError, match="超过3秒"):
        build_paper_limit_proposal(
            authorization=_authorization(),
            best_ask=12.34,
            quote_market_time=WINDOW_START - timedelta(seconds=4),
            quote_received_at=WINDOW_START,
        )
    with pytest.raises(ValueError, match="提交窗口"):
        build_paper_limit_proposal(
            authorization=_authorization(),
            best_ask=12.34,
            quote_market_time=WINDOW_START - timedelta(seconds=1),
            quote_received_at=WINDOW_START - timedelta(seconds=1),
        )


def test_final_approval_never_allows_price_chasing_or_stale_submit() -> None:
    proposal = _proposal()
    approval = _approval()
    now = WINDOW_START + timedelta(seconds=3)
    validate_submission_approval(
        proposal=proposal,
        approval=approval,
        authorization=_authorization(),
        fresh_best_ask=12.34,
        quote_market_time=now - timedelta(seconds=1),
        now=now,
    )
    with pytest.raises(ValueError, match="禁止追价"):
        validate_submission_approval(
            proposal=proposal,
            approval=approval,
            authorization=_authorization(),
            fresh_best_ask=12.35,
            quote_market_time=now,
            now=now,
        )
    with pytest.raises(ValueError, match="超过3秒"):
        validate_submission_approval(
            proposal=proposal,
            approval=approval,
            authorization=_authorization(),
            fresh_best_ask=12.34,
            quote_market_time=now - timedelta(seconds=4),
            now=now,
        )
