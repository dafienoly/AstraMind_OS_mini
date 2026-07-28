from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from astramind_mini.portfolio_risk.application.tactical_target import build_tactical_target
from astramind_mini.trading_execution.adapters import ContinuousShadowStore
from astramind_mini.trading_execution.adapters.miniqmt_account_normalization import (
    build_account_snapshot,
)
from astramind_mini.trading_execution.application import ContinuousShadowService
from astramind_mini.trading_execution.contracts.account import (
    AccountMode,
    AccountSnapshot,
    LocalAccountProjection,
    ReconciliationReport,
)
from astramind_mini.trading_execution.contracts.continuous_shadow import (
    ContinuousShadowState,
    ReconciliationDisposition,
    ShadowStatePosition,
)
from astramind_mini.trading_execution.domain import (
    assess_drawdown,
    build_continuous_shadow_order_plan,
    initial_continuous_shadow_state,
    isolate_broker_simulation_state,
    reconcile_account,
    roll_shadow_trading_day,
    start_continuous_shadow_cycle,
    synthetic_shadow_projection,
)
from astramind_mini.trading_execution.domain.shadow import ShadowQuote

NOW = datetime(2026, 7, 28, 8, tzinfo=UTC)
HASH_A = "sha256:" + "a" * 64


def _snapshot(
    *,
    position: bool = True,
    mode: AccountMode = "simulation",
) -> AccountSnapshot:
    positions: list[object] = (
        [
            {
                "instrument_id": "000001.SZ",
                "quantity": 200,
                "available_quantity": 100,
                "frozen_quantity": 0,
                "average_price": 10.0,
                "market_value_cny": 2_000.0,
            }
        ]
        if position
        else []
    )
    return build_account_snapshot(
        account_mode=mode,
        account_fingerprint=HASH_A,
        as_of=NOW,
        asset={
            "cash_cny": 20_000,
            "frozen_cash_cny": 0,
            "market_value_cny": 2_000 if position else 0,
            "total_asset_cny": 22_000 if position else 20_000,
        },
        positions=positions,
        orders=[],
        trades=[],
        client_version="test",
        gateway_version="test",
    )


def _initialized() -> tuple[
    LocalAccountProjection,
    AccountSnapshot,
    ReconciliationReport,
    ReconciliationDisposition,
    ContinuousShadowState,
]:
    local = synthetic_shadow_projection(as_of=NOW)
    snapshot = _snapshot()
    report = reconcile_account(local, snapshot, created_at=NOW)
    disposition = isolate_broker_simulation_state(local, snapshot, report)
    state = initial_continuous_shadow_state(
        local,
        disposition,
        trading_date=date(2026, 7, 28),
    )
    return local, snapshot, report, disposition, state


def test_broker_difference_is_isolated_without_adopting_position() -> None:
    local, _, report, disposition, state = _initialized()

    assert report.blocker_codes == ("cash_difference", "position_difference")
    assert disposition.resolved_blocker_codes == report.blocker_codes
    assert disposition.local_shadow_allowed is True
    assert disposition.broker_actions_allowed is False
    assert disposition.local_projection_id == local.projection_id
    assert state.cash_cny == 50_000
    assert state.positions == ()


def test_live_account_cannot_seed_local_shadow() -> None:
    local = synthetic_shadow_projection(as_of=NOW)
    snapshot = _snapshot(mode="live")
    report = reconcile_account(local, snapshot, created_at=NOW)

    with pytest.raises(ValueError, match="只允许隔离模拟盘"):
        isolate_broker_simulation_state(local, snapshot, report)


@pytest.mark.parametrize(
    ("equity", "level", "buys", "proposal"),
    [
        (46_500, "normal", True, False),
        (46_000, "warning", True, False),
        (45_000, "freeze_new", False, False),
        (44_000, "liquidation_proposal", False, True),
    ],
)
def test_drawdown_actions_are_frozen(
    equity: float,
    level: str,
    buys: bool,
    proposal: bool,
) -> None:
    *_, state = _initialized()
    state = state.model_copy(
        update={
            "equity_cny": equity,
            "account_equity_cny": equity,
        }
    )
    decision = assess_drawdown(state, created_at=NOW)

    assert decision.level == level
    assert decision.all_buys_allowed is buys
    assert decision.liquidation_proposal_required is proposal
    assert decision.automatic_liquidation_allowed is False


def test_order_plan_is_deterministic_cash_bounded_and_shadow_only() -> None:
    *_, state = _initialized()
    _, _, target, details = build_tactical_target(
        prediction_batch_ids=("prediction:test",),
        ranked_candidates=(("000002.SZ", 100.0),),
        as_of=NOW,
    )
    constrained = state.model_copy(update={"cash_cny": 1_000})
    decision = assess_drawdown(constrained, created_at=NOW)
    first = build_continuous_shadow_order_plan(
        target,
        details,
        constrained,
        decision,
        created_at=NOW,
        earliest_execution_date=date(2026, 7, 29),
    )
    second = build_continuous_shadow_order_plan(
        target,
        details,
        constrained,
        decision,
        created_at=NOW,
        earliest_execution_date=date(2026, 7, 29),
    )

    assert first == second
    assert first.order_plan.execution_mode == "shadow"
    assert first.broker_actions_allowed is False
    assert first.lines[0].executable_quantity == 0
    assert first.lines[0].blocker_codes == ("insufficient_cash",)


def test_sell_plan_respects_t_plus_one_available_quantity() -> None:
    *_, state = _initialized()
    position = ShadowStatePosition(
        instrument_id="000001.SZ",
        quantity=150,
        available_quantity=100,
        average_cost=10,
    )
    state = state.model_copy(update={"positions": (position,)})
    _, _, target, details = build_tactical_target(
        prediction_batch_ids=("prediction:test",),
        ranked_candidates=(),
        as_of=NOW,
    )
    decision = assess_drawdown(state, created_at=NOW)
    plan = build_continuous_shadow_order_plan(
        target,
        details,
        state,
        decision,
        created_at=NOW,
        earliest_execution_date=date(2026, 7, 29),
    )

    assert plan.status == "blocked"
    assert plan.lines[0].requested_quantity == 150
    assert plan.lines[0].executable_quantity == 100
    assert plan.lines[0].blocker_codes == ("t_plus_one_unavailable_quantity",)


def test_store_is_append_only_wal_and_restart_safe(tmp_path: Path) -> None:
    _, _, _, disposition, state = _initialized()
    database = tmp_path / "shadow.sqlite3"
    store = ContinuousShadowStore(database)
    store.publish_disposition(disposition)
    store.publish_state(state)
    store.publish_disposition(disposition)
    store.publish_state(state)

    restarted = ContinuousShadowStore(database)
    assert restarted.read_disposition(disposition.disposition_id) == disposition
    assert restarted.read_state(state.state_id) == state
    assert restarted.latest_state() == state
    assert restarted.counts() == (1, 1, 0)
    assert restarted.journal_mode().lower() == "wal"


def test_cycle_records_missed_nominal_open_without_broker_action(tmp_path: Path) -> None:
    *_, state = _initialized()
    _, _, target, details = build_tactical_target(
        prediction_batch_ids=("prediction:promoted-test",),
        ranked_candidates=(("000002.SZ", 10.0),),
        as_of=NOW,
    )
    decision = assess_drawdown(state, created_at=NOW)
    plan = build_continuous_shadow_order_plan(
        target,
        details,
        state,
        decision,
        created_at=NOW,
        earliest_execution_date=date(2026, 7, 29),
    )
    cycle = start_continuous_shadow_cycle(
        promotion_decision_id="promotion:test",
        data_snapshot_id="snapshot:test",
        feature_snapshot_id="feature-snapshot:test",
        prediction_batch_id="prediction-batch:test",
        target=target,
        plan=plan,
        signal_date=date(2026, 7, 27),
        nominal_execution_date=date(2026, 7, 28),
        scheduled_execution_date=date(2026, 7, 29),
        created_at=NOW,
    )
    store = ContinuousShadowStore(tmp_path / "shadow.sqlite3")
    store.publish_cycle(cycle)
    store.publish_cycle(cycle)

    assert cycle.status == "waiting_next_open"
    assert cycle.warning_codes == ("nominal_next_open_missed",)
    assert cycle.broker_actions_allowed is False
    assert store.read_cycle(cycle.cycle_id) == cycle
    assert store.cycle_count() == 1


def test_continuous_shadow_executes_locally_and_recovers_t_plus_one(tmp_path: Path) -> None:
    _, _, _, disposition, state = _initialized()
    store = ContinuousShadowStore(tmp_path / "shadow.sqlite3")
    store.publish_disposition(disposition)
    store.publish_state(state)
    service = ContinuousShadowService(store)
    _, _, target, details = build_tactical_target(
        prediction_batch_ids=("prediction:promoted-test",),
        ranked_candidates=(("000002.SZ", 10.0),),
        as_of=NOW,
    )
    plan = service.prepare_plan(
        target=target,
        details=details,
        state=state,
        created_at=NOW,
        earliest_execution_date=date(2026, 7, 29),
    )
    assert plan.status == "ready"

    execution_time = NOW + timedelta(days=1)
    filled = service.execute_plan(
        plan=plan,
        state=state,
        quotes={
            "000002.SZ": ShadowQuote(
                "000002.SZ",
                execution_time,
                10.0,
                10_000,
            )
        },
        now=execution_time,
    )
    assert filled.positions[0].quantity == 4_500
    assert filled.positions[0].available_quantity == 0

    rolled = roll_shadow_trading_day(
        filled,
        trading_date=date(2026, 7, 30),
        as_of=execution_time + timedelta(days=1),
    )
    store.publish_state(rolled)
    restarted = ContinuousShadowStore(tmp_path / "shadow.sqlite3")
    assert restarted.latest_state() == rolled
    assert rolled.positions[0].available_quantity == 4_500
    assert restarted.counts() == (1, 3, 1)
