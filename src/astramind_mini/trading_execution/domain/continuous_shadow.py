"""Pure reconciliation disposition, drawdown, and OrderPlan logic."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from astramind_mini.contracts import ExecutionMode, OrderPlan, PortfolioTarget
from astramind_mini.portfolio_risk.public import TacticalTargetDetails

from ..contracts.account import (
    AccountSnapshot,
    LocalAccountProjection,
    ReconciliationReport,
)
from ..contracts.continuous_shadow import (
    ContinuousShadowCycle,
    ContinuousShadowOrderPlan,
    ContinuousShadowState,
    DrawdownDecision,
    DrawdownLevel,
    ReconciliationDisposition,
    ShadowPlanLine,
    ShadowStatePosition,
)
from .reconciliation import canonical_hash

ALIGNMENT_POLICY_VERSION = "shadow-account-isolation-v1.0.0"


def isolate_broker_simulation_state(
    local: LocalAccountProjection,
    snapshot: AccountSnapshot,
    report: ReconciliationReport,
) -> ReconciliationDisposition:
    if snapshot.account_mode != "simulation" or report.account_mode != "simulation":
        raise ValueError("只允许隔离模拟盘状态，实盘账户不能成为本地 Shadow 起点")
    if report.account_snapshot_id != snapshot.account_snapshot_id:
        raise ValueError("对账报告与账户快照身份不一致")
    if report.local_projection_id != local.projection_id:
        raise ValueError("对账报告与本地投影身份不一致")
    allowed = {"cash_difference", "position_difference"}
    if not set(report.blocker_codes).issubset(allowed):
        raise ValueError("存在未解决的委托或其他账户阻断，不能推进本地 Shadow")
    if report.unexpected_open_order_fingerprints or report.missing_open_order_fingerprints:
        raise ValueError("存在未完成委托差异，不能隔离为外部模拟盘状态")
    identity = {
        "account_snapshot_id": snapshot.account_snapshot_id,
        "reconciliation_report_id": report.reconciliation_report_id,
        "local_projection_id": local.projection_id,
        "resolution_kind": "isolate_broker_simulation_state",
        "local_shadow_authority": "synthetic_shadow_ledger",
        "resolved_blocker_codes": sorted(report.blocker_codes),
        "policy_version": ALIGNMENT_POLICY_VERSION,
        "created_at": report.created_at,
    }
    digest = canonical_hash(identity)
    return ReconciliationDisposition(
        disposition_id="reconciliation-disposition:" + digest.removeprefix("sha256:"),
        account_snapshot_id=snapshot.account_snapshot_id,
        reconciliation_report_id=report.reconciliation_report_id,
        local_projection_id=local.projection_id,
        resolution_kind="isolate_broker_simulation_state",
        local_shadow_authority="synthetic_shadow_ledger",
        resolved_blocker_codes=tuple(sorted(report.blocker_codes)),
        policy_version=ALIGNMENT_POLICY_VERSION,
        created_at=report.created_at,
        content_hash=digest,
    )


def initial_continuous_shadow_state(
    local: LocalAccountProjection,
    disposition: ReconciliationDisposition,
    *,
    trading_date: date,
) -> ContinuousShadowState:
    if disposition.local_projection_id != local.projection_id:
        raise ValueError("差异处置与本地投影身份不一致")
    positions = tuple(
        ShadowStatePosition(
            instrument_id=item.instrument_id,
            quantity=item.quantity,
            available_quantity=item.available_quantity,
            average_cost=item.average_price or 0,
        )
        for item in local.positions
    )
    identity = {
        "disposition_id": disposition.disposition_id,
        "trading_date": trading_date,
        "as_of": local.as_of,
        "cash_cny": local.cash_cny,
        "positions": [item.model_dump(mode="json") for item in positions],
        "realized_profit_cny": 0.0,
        "equity_cny": local.cash_cny,
        "sleeve_peak_equity_cny": local.cash_cny,
        "account_equity_cny": local.cash_cny,
        "account_peak_equity_cny": local.cash_cny,
    }
    digest = canonical_hash(identity)
    return ContinuousShadowState(
        state_id="continuous-shadow-state:" + digest.removeprefix("sha256:"),
        disposition_id=disposition.disposition_id,
        trading_date=trading_date,
        as_of=local.as_of,
        cash_cny=local.cash_cny,
        positions=positions,
        realized_profit_cny=0.0,
        equity_cny=local.cash_cny,
        sleeve_peak_equity_cny=local.cash_cny,
        account_equity_cny=local.cash_cny,
        account_peak_equity_cny=local.cash_cny,
        content_hash=digest,
    )


def assess_drawdown(state: ContinuousShadowState, *, created_at: datetime) -> DrawdownDecision:
    sleeve = _drawdown(state.equity_cny, state.sleeve_peak_equity_cny)
    account = _drawdown(state.account_equity_cny, state.account_peak_equity_cny)
    effective = max(sleeve, account)
    if effective >= 0.12:
        level: DrawdownLevel = "liquidation_proposal"
    elif effective >= 0.10:
        level = "freeze_new"
    elif effective >= 0.08:
        level = "warning"
    else:
        level = "normal"
    identity = {
        "state_id": state.state_id,
        "sleeve_drawdown": sleeve,
        "account_drawdown": account,
        "effective_drawdown": effective,
        "level": level,
        "created_at": created_at,
    }
    digest = canonical_hash(identity)
    return DrawdownDecision(
        decision_id="drawdown-decision:" + digest.removeprefix("sha256:"),
        state_id=state.state_id,
        sleeve_drawdown=sleeve,
        account_drawdown=account,
        effective_drawdown=effective,
        level=level,
        expanding_risk_allowed=level == "normal",
        new_positions_allowed=level in {"normal", "warning"},
        all_buys_allowed=level in {"normal", "warning"},
        liquidation_proposal_required=level == "liquidation_proposal",
        created_at=created_at,
        content_hash=digest,
    )


def build_continuous_shadow_order_plan(
    target: PortfolioTarget,
    details: TacticalTargetDetails,
    state: ContinuousShadowState,
    decision: DrawdownDecision,
    *,
    created_at: datetime,
    earliest_execution_date: date,
) -> ContinuousShadowOrderPlan:
    if target.portfolio_target_id != details.portfolio_target_id:
        raise ValueError("目标组合与明细身份不一致")
    if decision.state_id != state.state_id:
        raise ValueError("回撤判断与 Shadow 状态身份不一致")
    desired = {
        item.instrument_id: int(
            (details.capital_cny * item.weight / item.reference_price) // 100 * 100
        )
        for item in details.holdings
    }
    references = {item.instrument_id: item.reference_price for item in details.holdings}
    current = {item.instrument_id: item for item in state.positions}
    lines = _plan_lines(
        desired,
        references,
        current,
        state,
        decision,
        earliest_execution_date,
    )
    identity = {
        "portfolio_target_id": target.portfolio_target_id,
        "state_id": state.state_id,
        "drawdown_decision_id": decision.decision_id,
        "lines": [line.model_dump(mode="json") for line in lines],
    }
    digest = canonical_hash(identity)
    plan = OrderPlan(
        order_plan_id="order-plan:" + digest.removeprefix("sha256:"),
        portfolio_target_id=target.portfolio_target_id,
        standing_mandate_id=None,
        execution_mode=ExecutionMode.SHADOW,
        created_at=created_at,
        content_hash=digest,
    )
    status: Literal["ready", "blocked", "no_action"] = (
        "no_action"
        if not lines
        else ("blocked" if any(line.blocker_codes for line in lines) else "ready")
    )
    return ContinuousShadowOrderPlan(
        order_plan=plan,
        state_id=state.state_id,
        drawdown_decision_id=decision.decision_id,
        status=status,
        lines=lines,
        content_hash=digest,
    )


def start_continuous_shadow_cycle(
    *,
    promotion_decision_id: str,
    data_snapshot_id: str,
    feature_snapshot_id: str,
    prediction_batch_id: str,
    target: PortfolioTarget,
    plan: ContinuousShadowOrderPlan,
    signal_date: date,
    nominal_execution_date: date,
    scheduled_execution_date: date,
    created_at: datetime,
) -> ContinuousShadowCycle:
    if plan.order_plan.portfolio_target_id != target.portfolio_target_id:
        raise ValueError("持续 Shadow 周期的目标与订单计划身份不一致")
    if scheduled_execution_date < nominal_execution_date:
        raise ValueError("计划执行日不能早于名义执行日")
    warnings = (
        ("nominal_next_open_missed",) if scheduled_execution_date > nominal_execution_date else ()
    )
    status: Literal["waiting_next_open", "no_action", "blocked"] = (
        "waiting_next_open"
        if plan.status == "ready"
        else ("no_action" if plan.status == "no_action" else "blocked")
    )
    identity = {
        "promotion_decision_id": promotion_decision_id,
        "data_snapshot_id": data_snapshot_id,
        "feature_snapshot_id": feature_snapshot_id,
        "prediction_batch_id": prediction_batch_id,
        "portfolio_target_id": target.portfolio_target_id,
        "order_plan_id": plan.order_plan.order_plan_id,
        "signal_date": signal_date,
        "nominal_execution_date": nominal_execution_date,
        "scheduled_execution_date": scheduled_execution_date,
        "status": status,
        "warning_codes": warnings,
        "created_at": created_at,
    }
    digest = canonical_hash(identity)
    return ContinuousShadowCycle(
        cycle_id="continuous-shadow-cycle:" + digest.removeprefix("sha256:"),
        promotion_decision_id=promotion_decision_id,
        data_snapshot_id=data_snapshot_id,
        feature_snapshot_id=feature_snapshot_id,
        prediction_batch_id=prediction_batch_id,
        portfolio_target_id=target.portfolio_target_id,
        order_plan_id=plan.order_plan.order_plan_id,
        signal_date=signal_date,
        nominal_execution_date=nominal_execution_date,
        scheduled_execution_date=scheduled_execution_date,
        status=status,
        warning_codes=warnings,
        created_at=created_at,
        content_hash=digest,
    )


def _plan_lines(
    desired: dict[str, int],
    references: dict[str, float],
    current: dict[str, ShadowStatePosition],
    state: ContinuousShadowState,
    decision: DrawdownDecision,
    earliest_execution_date: date,
) -> tuple[ShadowPlanLine, ...]:
    lines = []
    cash_remaining = state.cash_cny
    current_exposure = sum(item.quantity * max(item.average_cost, 0) for item in current.values())
    desired_exposure = sum(desired[key] * references[key] for key in desired)
    for instrument_id in sorted(set(current) | set(desired)):
        current_position = current.get(instrument_id)
        current_quantity = current_position.quantity if current_position else 0
        delta = desired.get(instrument_id, 0) - current_quantity
        if not delta:
            continue
        side: Literal["buy", "sell"] = "buy" if delta > 0 else "sell"
        requested = abs(delta)
        reference_price = references.get(
            instrument_id,
            current[instrument_id].average_cost if instrument_id in current else 0,
        )
        blockers: list[str] = []
        executable = requested
        if side == "sell":
            available = current[instrument_id].available_quantity
            executable = min(requested, available)
            if executable < requested:
                blockers.append("t_plus_one_unavailable_quantity")
        else:
            if not decision.all_buys_allowed:
                blockers.append("drawdown_buys_frozen")
            elif not decision.expanding_risk_allowed and desired_exposure > current_exposure:
                blockers.append("drawdown_risk_expansion")
            affordable = _affordable_quantity(cash_remaining, reference_price)
            executable = min(executable, affordable)
            if executable < requested:
                blockers.append("insufficient_cash")
            if executable:
                amount = executable * reference_price
                cash_remaining -= amount + max(5.0, amount * 0.0003)
        lines.append(
            ShadowPlanLine(
                instrument_id=instrument_id,
                side=side,
                requested_quantity=requested,
                executable_quantity=max(0, executable),
                reference_price=reference_price,
                earliest_execution_date=earliest_execution_date,
                blocker_codes=tuple(blockers),
            )
        )
    return tuple(lines)


def _drawdown(equity: float, peak: float) -> float:
    return round(max(0.0, (peak - equity) / peak), 8)


def _affordable_quantity(cash_cny: float, price: float) -> int:
    quantity = int(cash_cny // (price * 100)) * 100
    while quantity > 0:
        amount = quantity * price
        if amount + max(5.0, amount * 0.0003) <= cash_cny:
            return quantity
        quantity -= 100
    return 0


__all__ = [
    "ALIGNMENT_POLICY_VERSION",
    "assess_drawdown",
    "build_continuous_shadow_order_plan",
    "initial_continuous_shadow_state",
    "isolate_broker_simulation_state",
    "start_continuous_shadow_cycle",
]
