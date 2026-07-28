"""Application orchestration for account isolation and continuous Shadow."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict
from datetime import date, datetime, timedelta

from astramind_mini.contracts import PortfolioTarget
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
    ReconciliationDisposition,
)
from ..domain.continuous_shadow import (
    assess_drawdown,
    build_continuous_shadow_order_plan,
    initial_continuous_shadow_state,
    isolate_broker_simulation_state,
    start_continuous_shadow_cycle,
)
from ..domain.continuous_shadow_lifecycle import apply_shadow_fills
from ..domain.shadow import OrderSide, ShadowOrderLine, ShadowQuote
from ..ports.continuous_shadow import ContinuousShadowRepository
from .shadow import simulate_shadow


class ContinuousShadowService:
    def __init__(self, store: ContinuousShadowRepository) -> None:
        self._store = store

    def initialize(
        self,
        *,
        local: LocalAccountProjection,
        snapshot: AccountSnapshot,
        report: ReconciliationReport,
    ) -> tuple[ReconciliationDisposition, ContinuousShadowState]:
        disposition = isolate_broker_simulation_state(local, snapshot, report)
        state = initial_continuous_shadow_state(
            local,
            disposition,
            trading_date=snapshot.trading_date,
        )
        self._store.publish_disposition(disposition)
        self._store.publish_state(state)
        return disposition, state

    def prepare_plan(
        self,
        *,
        target: PortfolioTarget,
        details: TacticalTargetDetails,
        state: ContinuousShadowState,
        created_at: datetime,
        earliest_execution_date: date,
    ) -> ContinuousShadowOrderPlan:
        decision = assess_drawdown(state, created_at=created_at)
        plan = build_continuous_shadow_order_plan(
            target,
            details,
            state,
            decision,
            created_at=created_at,
            earliest_execution_date=earliest_execution_date,
        )
        self._store.publish_order_plan(plan)
        return plan

    def execute_plan(
        self,
        *,
        plan: ContinuousShadowOrderPlan,
        state: ContinuousShadowState,
        quotes: Mapping[str, ShadowQuote],
        now: datetime,
        stale_after: timedelta = timedelta(seconds=10),
    ) -> ContinuousShadowState:
        if plan.status != "ready":
            raise ValueError("只有无阻断的持续 Shadow 订单计划可以执行")
        lines = tuple(
            ShadowOrderLine(
                instrument_id=line.instrument_id,
                side=OrderSide(line.side),
                quantity=line.executable_quantity,
                reference_price=line.reference_price,
            )
            for line in plan.lines
            if line.executable_quantity > 0
        )
        fills, events = simulate_shadow(
            plan.order_plan,
            lines,
            quotes,
            now=now,
            stale_after=stale_after,
        )
        for fill, event in zip(fills, events, strict=True):
            self._store.append_shadow_event(event, asdict(fill))
        next_state = apply_shadow_fills(
            state,
            fills,
            as_of=now,
            trading_date=state.trading_date,
        )
        self._store.publish_state(next_state)
        return next_state

    def start_cycle(
        self,
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
        cycle = start_continuous_shadow_cycle(
            promotion_decision_id=promotion_decision_id,
            data_snapshot_id=data_snapshot_id,
            feature_snapshot_id=feature_snapshot_id,
            prediction_batch_id=prediction_batch_id,
            target=target,
            plan=plan,
            signal_date=signal_date,
            nominal_execution_date=nominal_execution_date,
            scheduled_execution_date=scheduled_execution_date,
            created_at=created_at,
        )
        self._store.publish_cycle(cycle)
        return cycle


__all__ = ["ContinuousShadowService"]
