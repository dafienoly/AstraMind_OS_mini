"""Pure construction and reconciliation for the first real Paper canary."""

from __future__ import annotations

from datetime import datetime

from astramind_mini.contracts import ExecutionMode, OrderPlan

from ..contracts.account import AccountSnapshot
from ..contracts.paper import PaperOrderProjection, PaperPreflightDecision
from ..contracts.paper_canary import PaperCanaryAuthorization
from ..contracts.paper_continuous import PaperLimitProposal, PaperSubmissionApproval
from ..contracts.paper_runtime import PaperConvergenceReport
from ..contracts.paper_startup import BrokerAccountModeLock, PaperAccountBaseline
from .paper import build_paper_preflight
from .reconciliation import canonical_hash


def build_submission_approval(
    *,
    proposal: PaperLimitProposal,
    authorization: PaperCanaryAuthorization,
    confirmed_limit_price: float,
    approved_at: datetime,
    effective_to: datetime,
) -> PaperSubmissionApproval:
    if proposal.authorization_id != authorization.authorization_id:
        raise ValueError("限价提案与 Paper 授权不一致")
    if confirmed_limit_price != proposal.exact_limit_price:
        raise ValueError("确认限价必须与展示的确切限价一致")
    if (
        not authorization.submission_window_start
        <= approved_at
        <= authorization.submission_window_end
    ):
        raise ValueError("最终批准时间不在提交窗口")
    if effective_to > authorization.submission_window_end:
        raise ValueError("最终批准不能越过提交窗口")
    payload = {
        "proposal_id": proposal.proposal_id,
        "authorization_id": authorization.authorization_id,
        "exact_limit_price": confirmed_limit_price,
        "approved_at": approved_at,
        "effective_to": effective_to,
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


def build_real_paper_preflight(
    *,
    authorization: PaperCanaryAuthorization,
    proposal: PaperLimitProposal,
    approval: PaperSubmissionApproval,
    mode_lock: BrokerAccountModeLock,
    baseline: PaperAccountBaseline,
    account: AccountSnapshot,
    quote_market_time: datetime,
    quote_received_at: datetime,
    quote_tradable: bool,
    now: datetime,
    account_drawdown: float,
) -> PaperPreflightDecision:
    open_orders = tuple(item for item in account.orders if item.is_open)
    expected_notional = approval.exact_limit_price * authorization.quantity
    checks = {
        "account_mode_verified": (
            mode_lock.effective_mode == account.account_mode == authorization.account_mode
            and baseline.mode_lock_id == mode_lock.mode_lock_id
            and baseline.account_snapshot_id == account.account_snapshot_id
        ),
        "reconciliation_matched": (
            not baseline.open_order_fingerprints
            and not open_orders
            and baseline.baseline_id == proposal.account_baseline_id
        ),
        "quote_fresh": (
            quote_market_time <= quote_received_at <= now
            and (now - quote_market_time).total_seconds() <= authorization.quote_max_age_seconds
        ),
        "trading_window_open": (
            authorization.submission_window_start <= now <= authorization.submission_window_end
        ),
        "tradable": quote_tradable,
        "cash_sufficient": account.cash.cash_cny >= expected_notional + 10,
        "lot_valid": authorization.quantity % 100 == 0,
        "t_plus_one_valid": authorization.side == "buy",
        "drawdown_allowed": 0 <= account_drawdown < 0.08,
        "mandate_approved": (
            approval.authorization_id == authorization.authorization_id
            and approval.proposal_id == proposal.proposal_id
            and approval.exact_limit_price == proposal.exact_limit_price
            and now <= approval.effective_to
            and expected_notional <= authorization.max_notional_cny
        ),
    }
    evidence_ids = (
        authorization.authorization_id,
        proposal.proposal_id,
        approval.approval_id,
        mode_lock.mode_lock_id,
        baseline.baseline_id,
        account.account_snapshot_id,
    )
    return build_paper_preflight(
        created_at=now,
        checks=checks,
        evidence_kind="real_miniqmt",
        evidence_ids=evidence_ids,
    )


def build_paper_canary_order_plan(
    *,
    authorization: PaperCanaryAuthorization,
    approval: PaperSubmissionApproval,
    preflight: PaperPreflightDecision,
) -> OrderPlan:
    if preflight.evidence_kind != "real_miniqmt" or preflight.blocker_codes:
        raise ValueError("真实 Paper 预检未通过")
    if approval.authorization_id != authorization.authorization_id:
        raise ValueError("最终批准与 StandingMandate 不一致")
    payload = {
        "portfolio_target_id": authorization.source_portfolio_target_id,
        "standing_mandate_id": authorization.standing_mandate.standing_mandate_id,
        "execution_mode": ExecutionMode.PAPER,
        "authorization_id": authorization.authorization_id,
        "approval_id": approval.approval_id,
        "created_at": approval.approved_at,
    }
    digest = canonical_hash(payload)
    return OrderPlan(
        order_plan_id="order-plan:" + digest[7:],
        portfolio_target_id=authorization.source_portfolio_target_id,
        standing_mandate_id=authorization.standing_mandate.standing_mandate_id,
        execution_mode=ExecutionMode.PAPER,
        created_at=approval.approved_at,
        content_hash=digest,
    )


def account_drawdown(current: AccountSnapshot, history: tuple[AccountSnapshot, ...]) -> float:
    peak = max((item.cash.total_asset_cny for item in (*history, current)), default=0)
    if peak <= 0:
        return 1.0
    return max(0.0, 1 - current.cash.total_asset_cny / peak)


def build_convergence_report(
    *,
    intent_id: str,
    instrument_id: str,
    starting: AccountSnapshot,
    ending: AccountSnapshot,
    projection: PaperOrderProjection,
    created_at: datetime,
) -> PaperConvergenceReport:
    fingerprint = projection.broker_order_fingerprint
    trades = tuple(
        item for item in ending.trades if fingerprint and item.order_fingerprint == fingerprint
    )
    open_orders = tuple(
        item
        for item in ending.orders
        if item.is_open and fingerprint and item.order_fingerprint == fingerprint
    )
    start_quantity = _quantity(starting, instrument_id)
    end_quantity = _quantity(ending, instrument_id)
    broker_quantity = sum(item.quantity for item in trades)
    trade_amount = round(sum(item.amount_cny for item in trades), 2)
    managed = max(0, end_quantity - start_quantity)
    cash_spent = round(starting.cash.cash_cny - ending.cash.cash_cny, 2)
    blockers: list[str] = []
    if projection.state not in {"filled", "cancelled", "rejected"}:
        blockers.append("paper_order_not_terminal")
    if open_orders:
        blockers.append("canary_order_still_open")
    if broker_quantity != projection.cumulative_filled_quantity:
        blockers.append("broker_fill_projection_difference")
    if managed != broker_quantity:
        blockers.append("managed_position_difference")
    tolerance = max(100.0, trade_amount * 0.002)
    if broker_quantity == 0 and abs(cash_spent) > 0.01:
        blockers.append("cash_difference_without_fill")
    if broker_quantity and not trade_amount - 0.01 <= cash_spent <= trade_amount + tolerance:
        blockers.append("cash_trade_amount_difference")
    payload = {
        "intent_id": intent_id,
        "starting_account_snapshot_id": starting.account_snapshot_id,
        "ending_account_snapshot_id": ending.account_snapshot_id,
        "projection_id": projection.projection_id,
        "instrument_id": instrument_id,
        "starting_quantity": start_quantity,
        "ending_quantity": end_quantity,
        "inherited_quantity": start_quantity,
        "managed_quantity": managed,
        "projected_filled_quantity": projection.cumulative_filled_quantity,
        "broker_trade_quantity": broker_quantity,
        "starting_cash_cny": starting.cash.cash_cny,
        "ending_cash_cny": ending.cash.cash_cny,
        "broker_trade_amount_cny": trade_amount,
        "open_canary_order_count": len(open_orders),
        "status": "blocked" if blockers else "converged",
        "blocker_codes": tuple(sorted(blockers)),
        "created_at": created_at,
    }
    digest = canonical_hash(payload)
    return PaperConvergenceReport.model_validate(
        {
            "report_id": "paper-convergence-report:" + digest[7:],
            "content_hash": digest,
            **payload,
        }
    )


def _quantity(snapshot: AccountSnapshot, instrument_id: str) -> int:
    return sum(item.quantity for item in snapshot.positions if item.instrument_id == instrument_id)


def validate_canary_control_scope(
    *,
    intent_instrument_id: str,
    intent_quantity: int,
    intent_limit_price: float,
    intent_portfolio_target_id: str,
    intent_standing_mandate_id: str | None,
    approval: PaperSubmissionApproval,
    proposal: PaperLimitProposal,
    authorization: PaperCanaryAuthorization,
) -> None:
    if (
        intent_instrument_id != authorization.instrument_id
        or intent_quantity != authorization.quantity
        or intent_limit_price != approval.exact_limit_price
        or intent_portfolio_target_id != authorization.source_portfolio_target_id
        or intent_standing_mandate_id != authorization.standing_mandate.standing_mandate_id
        or proposal.authorization_id != authorization.authorization_id
        or approval.proposal_id != proposal.proposal_id
    ):
        raise ValueError("paper_canary_control_scope_mismatch")


__all__ = [
    "account_drawdown",
    "build_convergence_report",
    "build_paper_canary_order_plan",
    "build_real_paper_preflight",
    "build_submission_approval",
    "validate_canary_control_scope",
]
