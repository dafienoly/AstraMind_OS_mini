"""Advance one continuous Shadow cycle from entry through horizon exit."""

from __future__ import annotations

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from astramind_mini.contracts import PortfolioTarget
from astramind_mini.data.public import ShadowMarketObservation
from astramind_mini.portfolio_risk.public import TacticalTargetDetails

from ..contracts.continuous_shadow import (
    ContinuousShadowCycle,
    ContinuousShadowOrderPlan,
    ContinuousShadowState,
)
from ..contracts.shadow_cycle import (
    ShadowCycleCheckpoint,
    ShadowCycleResult,
    ShadowCycleStatus,
)
from ..domain.continuous_shadow_lifecycle import roll_shadow_trading_day
from ..domain.reconciliation import canonical_hash
from ..domain.shadow_cycle import (
    build_shadow_cycle_checkpoint,
    mark_shadow_session,
    maximum_drawdown,
    shadow_fill_blockers,
    shadow_quotes,
)
from ..ports.continuous_shadow import ContinuousShadowRepository
from .continuous_shadow import ContinuousShadowService

SHANGHAI = ZoneInfo("Asia/Shanghai")


class ShadowCycleCompletionService:
    def __init__(self, store: ContinuousShadowRepository) -> None:
        self._store = store
        self._execution = ContinuousShadowService(store)

    def advance_session(
        self,
        *,
        cycle: ContinuousShadowCycle,
        target: PortfolioTarget,
        entry_plan: ContinuousShadowOrderPlan,
        observations: tuple[ShadowMarketObservation, ...],
        trading_date: date,
        horizon_sessions: int,
        capital_cny: float,
    ) -> tuple[ShadowCycleCheckpoint, ShadowCycleResult | None]:
        self._validate(cycle, target, entry_plan, observations, trading_date, horizon_sessions)
        prior = self._store.latest_checkpoint(cycle.cycle_id)
        if prior is not None and trading_date == prior.trading_date:
            return prior, self._store.read_result_for_cycle(cycle.cycle_id)
        if prior is not None and (
            trading_date < prior.trading_date
            or prior.status in {"completed", "completed_no_entry", "blocked"}
        ):
            raise ValueError("持续 Shadow 周期不能倒退或越过终态")

        state_id = prior.state_id if prior is not None else entry_plan.state_id
        state = self._store.read_state(state_id)
        open_at = datetime.combine(trading_date, time(9, 30), SHANGHAI)
        if state.trading_date < trading_date:
            state = roll_shadow_trading_day(state, trading_date=trading_date, as_of=open_at)
            self._store.publish_state(state)
        sessions = 1 if prior is None else prior.sessions_elapsed + 1

        if prior is None:
            checkpoint = self._enter(
                cycle, entry_plan, state, observations, trading_date, sessions, open_at
            )
        elif prior.status == "active" and sessions < horizon_sessions:
            checkpoint = self._value(cycle, entry_plan, state, observations, trading_date, sessions)
        else:
            checkpoint = self._exit(
                cycle,
                target,
                entry_plan,
                state,
                observations,
                trading_date,
                sessions,
                capital_cny,
                open_at,
            )
        self._store.publish_checkpoint(checkpoint)
        result = self._terminal_result(cycle, entry_plan, checkpoint)
        if result is not None:
            self._store.publish_result(result)
        return checkpoint, result

    def _enter(
        self,
        cycle: ContinuousShadowCycle,
        plan: ContinuousShadowOrderPlan,
        state: ContinuousShadowState,
        observations: tuple[ShadowMarketObservation, ...],
        trading_date: date,
        sessions: int,
        open_at: datetime,
    ) -> ShadowCycleCheckpoint:
        next_state, fills, _ = self._execution.execute_plan_with_result(
            plan=plan,
            state=state,
            quotes=shadow_quotes(observations, "buy", open_at),
            now=open_at,
        )
        blockers = shadow_fill_blockers(fills)
        status: ShadowCycleStatus = "active" if next_state.positions else "completed_no_entry"
        valued, valuation_blockers = mark_shadow_session(next_state, observations, trading_date)
        self._store.publish_state(valued)
        return build_shadow_cycle_checkpoint(
            cycle=cycle,
            observations=observations,
            trading_date=trading_date,
            phase="entry",
            status=status,
            state=valued,
            sessions=sessions,
            entry_order_plan_id=plan.order_plan.order_plan_id,
            exit_order_plan_id=None,
            event_count=len(fills),
            blocker_codes=tuple(sorted(set(blockers) | set(valuation_blockers))),
        )

    def _value(
        self,
        cycle: ContinuousShadowCycle,
        plan: ContinuousShadowOrderPlan,
        state: ContinuousShadowState,
        observations: tuple[ShadowMarketObservation, ...],
        trading_date: date,
        sessions: int,
    ) -> ShadowCycleCheckpoint:
        valued, valuation_blockers = mark_shadow_session(state, observations, trading_date)
        self._store.publish_state(valued)
        return build_shadow_cycle_checkpoint(
            cycle=cycle,
            observations=observations,
            trading_date=trading_date,
            phase="valuation",
            status="active",
            state=valued,
            sessions=sessions,
            entry_order_plan_id=plan.order_plan.order_plan_id,
            exit_order_plan_id=None,
            event_count=0,
            blocker_codes=valuation_blockers,
        )

    def _exit(
        self,
        cycle: ContinuousShadowCycle,
        target: PortfolioTarget,
        entry_plan: ContinuousShadowOrderPlan,
        state: ContinuousShadowState,
        observations: tuple[ShadowMarketObservation, ...],
        trading_date: date,
        sessions: int,
        capital_cny: float,
        open_at: datetime,
    ) -> ShadowCycleCheckpoint:
        details = TacticalTargetDetails(target.portfolio_target_id, capital_cny, (), 1.0)
        exit_plan = self._execution.prepare_plan(
            target=target,
            details=details,
            state=state,
            created_at=open_at,
            earliest_execution_date=trading_date,
        )
        next_state, fills, _ = self._execution.execute_plan_with_result(
            plan=exit_plan,
            state=state,
            quotes=shadow_quotes(observations, "sell", open_at),
            now=open_at,
        )
        status: ShadowCycleStatus = "exit_waiting" if next_state.positions else "completed"
        valued, valuation_blockers = mark_shadow_session(next_state, observations, trading_date)
        self._store.publish_state(valued)
        return build_shadow_cycle_checkpoint(
            cycle=cycle,
            observations=observations,
            trading_date=trading_date,
            phase="exit",
            status=status,
            state=valued,
            sessions=sessions,
            entry_order_plan_id=entry_plan.order_plan.order_plan_id,
            exit_order_plan_id=exit_plan.order_plan.order_plan_id,
            event_count=len(fills),
            blocker_codes=tuple(sorted(set(shadow_fill_blockers(fills)) | set(valuation_blockers))),
        )

    def _terminal_result(
        self,
        cycle: ContinuousShadowCycle,
        entry_plan: ContinuousShadowOrderPlan,
        terminal: ShadowCycleCheckpoint,
    ) -> ShadowCycleResult | None:
        if terminal.status not in {"completed", "completed_no_entry"}:
            return None
        checkpoints = self._store.checkpoints_for(cycle.cycle_id)
        initial = self._store.read_state(entry_plan.state_id)
        final = self._store.read_state(terminal.state_id)
        equities = [initial.equity_cny]
        equities.extend(self._store.read_state(item.state_id).equity_cny for item in checkpoints)
        drawdown = maximum_drawdown(equities)
        identity = {
            "cycle_id": cycle.cycle_id,
            "status": terminal.status,
            "initial_state_id": initial.state_id,
            "terminal_state_id": final.state_id,
            "entry_date": cycle.scheduled_execution_date,
            "exit_date": terminal.trading_date if terminal.status == "completed" else None,
            "sessions_elapsed": terminal.sessions_elapsed,
            "initial_equity_cny": initial.equity_cny,
            "terminal_equity_cny": final.equity_cny,
            "total_return": round(final.equity_cny / initial.equity_cny - 1, 10),
            "realized_profit_cny": final.realized_profit_cny,
            "maximum_drawdown": drawdown,
            "checkpoint_count": len(checkpoints),
            "execution_event_count": self._store.event_count_for_cycle(cycle.cycle_id),
            "completed_at": terminal.recorded_at,
        }
        digest = canonical_hash(identity)
        return ShadowCycleResult.model_validate(
            {
                "result_id": "shadow-cycle-result:" + digest.removeprefix("sha256:"),
                "content_hash": digest,
                **identity,
            }
        )

    @staticmethod
    def _validate(
        cycle: ContinuousShadowCycle,
        target: PortfolioTarget,
        plan: ContinuousShadowOrderPlan,
        observations: tuple[ShadowMarketObservation, ...],
        trading_date: date,
        horizon_sessions: int,
    ) -> None:
        if horizon_sessions < 2:
            raise ValueError("持续 Shadow 观察周期至少需要两个交易日")
        if trading_date < cycle.scheduled_execution_date:
            raise ValueError("不能在计划执行日前推进持续 Shadow")
        if cycle.order_plan_id != plan.order_plan.order_plan_id:
            raise ValueError("持续 Shadow 周期与入口订单计划不一致")
        if cycle.portfolio_target_id != target.portfolio_target_id:
            raise ValueError("持续 Shadow 周期与目标组合不一致")
        if not observations:
            raise ValueError("Shadow 交易日缺少全部目标证券的可用状态证据")
        if any(
            item.data_snapshot_id != observations[0].data_snapshot_id
            or item.trade_date != trading_date
            for item in observations
        ):
            raise ValueError("Shadow 日度观察混用了快照或交易日")


__all__ = ["ShadowCycleCompletionService"]
