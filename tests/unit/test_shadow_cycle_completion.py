from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from astramind_mini.contracts import PortfolioTarget
from astramind_mini.data.public import ShadowMarketObservation
from astramind_mini.portfolio_risk.application.tactical_target import build_tactical_target
from astramind_mini.trading_execution.adapters import ContinuousShadowStore
from astramind_mini.trading_execution.adapters.miniqmt_account_normalization import (
    build_account_snapshot,
)
from astramind_mini.trading_execution.application import (
    ContinuousShadowService,
    ShadowCycleCompletionService,
)
from astramind_mini.trading_execution.contracts import (
    ContinuousShadowCycle,
    ContinuousShadowOrderPlan,
)
from astramind_mini.trading_execution.domain import (
    reconcile_account,
    synthetic_shadow_projection,
)

NOW = datetime(2026, 7, 28, 8, tzinfo=UTC)
HASH_A = "sha256:" + "a" * 64
SNAPSHOT_ID = "snapshot:sha256:" + "b" * 64


def _cycle(
    tmp_path: Path,
) -> tuple[
    ContinuousShadowStore,
    ShadowCycleCompletionService,
    ContinuousShadowCycle,
    PortfolioTarget,
    ContinuousShadowOrderPlan,
]:
    local = synthetic_shadow_projection(as_of=NOW)
    snapshot = build_account_snapshot(
        account_mode="simulation",
        account_fingerprint=HASH_A,
        as_of=NOW,
        asset={
            "cash_cny": 20_000,
            "frozen_cash_cny": 0,
            "market_value_cny": 0,
            "total_asset_cny": 20_000,
        },
        positions=[],
        orders=[],
        trades=[],
        client_version="test",
        gateway_version="test",
    )
    report = reconcile_account(local, snapshot, created_at=NOW)
    store = ContinuousShadowStore(tmp_path / "shadow.sqlite3")
    shadow = ContinuousShadowService(store)
    _, state = shadow.initialize(local=local, snapshot=snapshot, report=report)
    _, _, target, details = build_tactical_target(
        prediction_batch_ids=("prediction:test",),
        ranked_candidates=(("000001.SZ", 10.0),),
        as_of=NOW,
    )
    plan = shadow.prepare_plan(
        target=target,
        details=details,
        state=state,
        created_at=NOW,
        earliest_execution_date=date(2026, 7, 29),
    )
    cycle = shadow.start_cycle(
        promotion_decision_id="promotion:test",
        data_snapshot_id="snapshot:source",
        feature_snapshot_id="feature:test",
        prediction_batch_id="prediction:test",
        target=target,
        plan=plan,
        signal_date=date(2026, 7, 27),
        nominal_execution_date=date(2026, 7, 28),
        scheduled_execution_date=date(2026, 7, 29),
        created_at=NOW,
    )
    return store, ShadowCycleCompletionService(store), cycle, target, plan


def _observation(
    trade_date: date,
    *,
    open_price: float | None = 10.0,
    close_price: float | None = 10.2,
    state: str = "tradable",
) -> ShadowMarketObservation:
    return ShadowMarketObservation.model_validate(
        {
            "data_snapshot_id": SNAPSHOT_ID,
            "instrument_id": "000001.SZ",
            "trade_date": trade_date,
            "available_at": datetime.combine(
                trade_date,
                datetime.min.time(),
                UTC,
            )
            + timedelta(hours=10),
            "open_price": open_price,
            "close_price": close_price,
            "amount_cny": 2_000_000,
            "buy_state": state,
            "sell_state": state,
            "has_daily_bar": open_price is not None,
        }
    )


def test_ten_session_cycle_enters_values_exits_and_recovers(tmp_path: Path) -> None:
    store, service, cycle, target, plan = _cycle(tmp_path)
    result = None
    checkpoint = None
    start = date(2026, 7, 29)
    for offset in range(10):
        trade_date = start + timedelta(days=offset)
        checkpoint, result = service.advance_session(
            cycle=cycle,
            target=target,
            entry_plan=plan,
            observations=(
                _observation(
                    trade_date,
                    open_price=10.0 if offset == 0 else 11.0,
                    close_price=10.2 + offset * 0.1,
                ),
            ),
            trading_date=trade_date,
            horizon_sessions=10,
            capital_cny=50_000,
        )

    assert checkpoint is not None
    assert checkpoint.status == "completed"
    assert checkpoint.phase == "exit"
    assert checkpoint.sessions_elapsed == 10
    assert result is not None
    assert result.status == "completed"
    assert result.checkpoint_count == 10
    assert result.execution_event_count == 2
    assert result.total_return > 0
    assert result.broker_actions_allowed is False
    assert store.read_state(result.terminal_state_id).positions == ()

    same_checkpoint, same_result = service.advance_session(
        cycle=cycle,
        target=target,
        entry_plan=plan,
        observations=(_observation(start + timedelta(days=9), open_price=11.0),),
        trading_date=start + timedelta(days=9),
        horizon_sessions=10,
        capital_cny=50_000,
    )
    assert same_checkpoint == checkpoint
    assert same_result == result
    restarted = ContinuousShadowStore(tmp_path / "shadow.sqlite3")
    assert restarted.read_result_for_cycle(cycle.cycle_id) == result
    assert len(restarted.checkpoints_for(cycle.cycle_id)) == 10


def test_suspended_horizon_exit_is_deferred_without_fake_valuation(tmp_path: Path) -> None:
    _, service, cycle, target, plan = _cycle(tmp_path)
    entry_date = date(2026, 7, 29)
    service.advance_session(
        cycle=cycle,
        target=target,
        entry_plan=plan,
        observations=(_observation(entry_date),),
        trading_date=entry_date,
        horizon_sessions=2,
        capital_cny=50_000,
    )
    suspended_date = entry_date + timedelta(days=1)
    waiting, result = service.advance_session(
        cycle=cycle,
        target=target,
        entry_plan=plan,
        observations=(
            _observation(
                suspended_date,
                open_price=None,
                close_price=None,
                state="suspended",
            ),
        ),
        trading_date=suspended_date,
        horizon_sessions=2,
        capital_cny=50_000,
    )

    assert waiting.status == "exit_waiting"
    assert waiting.blocker_codes == (
        "missing_close_valuation:000001.SZ",
        "no_quote",
    )
    assert result is None

    exit_date = suspended_date + timedelta(days=1)
    completed, result = service.advance_session(
        cycle=cycle,
        target=target,
        entry_plan=plan,
        observations=(_observation(exit_date, open_price=9.8, close_price=9.9),),
        trading_date=exit_date,
        horizon_sessions=2,
        capital_cny=50_000,
    )
    assert completed.status == "completed"
    assert result is not None
    assert result.exit_date == exit_date
    assert result.sessions_elapsed == 3
