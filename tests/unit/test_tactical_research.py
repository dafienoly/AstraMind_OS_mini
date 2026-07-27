"""Focused proof for the point-in-time universe and tactical backtest engine."""

from collections.abc import Sequence
from datetime import date, timedelta

import pytest

from astramind_mini.strategy_research.application.backtest import DailyBacktestEngine
from astramind_mini.strategy_research.application.identity import (
    build_prediction_batch,
    freeze_strategy_version,
)
from astramind_mini.strategy_research.application.strategies import (
    event_attention_signal,
    momentum_breakout_signal,
    reversal_volume_price_signal,
)
from astramind_mini.strategy_research.application.universe import evaluate_universe
from astramind_mini.strategy_research.domain.backtest_models import (
    BacktestAssumptions,
    CandidateSignal,
    ResearchBar,
    UniverseRules,
)


def _bar(
    index: int,
    *,
    close: float = 10,
    amount: float = 100_000_000,
    instrument: str = "SYNTHETIC.SZ",
    buy_state: str = "tradable",
    sell_state: str = "tradable",
    risk_status: str = "normal",
) -> ResearchBar:
    return ResearchBar(
        instrument_id=instrument,
        trade_date=date(2020, 1, 1) + timedelta(days=index),
        open=close,
        high=close * 1.01,
        low=close * 0.99,
        close=close,
        research_close_index=close,
        amount_cny=amount,
        turnover_rate=1.0,
        listed_sessions=index + 100,
        risk_status=risk_status,
        buy_state=buy_state,
        sell_state=sell_state,
    )


def _always_signal(
    history: Sequence[ResearchBar],
    horizon: int,
) -> CandidateSignal | None:
    if len(history) != 21:
        return None
    latest = history[-1]
    return CandidateSignal(
        instrument_id=latest.instrument_id,
        signal_date=latest.trade_date,
        family="synthetic",
        horizon_sessions=horizon,
        score=1,
        reasons=("fixture",),
    )


def test_universe_is_point_in_time_and_event_channel_only_waives_liquidity() -> None:
    history = [_bar(index, amount=2_000_000) for index in range(20)]
    decision = evaluate_universe(history, UniverseRules(), event_attention=True)
    assert not decision.eligible
    assert decision.event_channel_eligible
    assert decision.reasons == ("insufficient_liquidity",)

    st_history = [*history[:-1], _bar(19, amount=2_000_000, risk_status="st")]
    st_decision = evaluate_universe(st_history, UniverseRules(), event_attention=True)
    assert not st_decision.event_channel_eligible
    assert "special_treatment_or_unknown" in st_decision.reasons


def test_signal_is_executed_only_at_next_session_open_with_board_lots_and_costs() -> None:
    bars = [_bar(index, close=10 + index * 0.01) for index in range(24)]
    result = DailyBacktestEngine().run(
        bars=bars,
        strategy_family="synthetic",
        horizon_sessions=2,
        signal_function=_always_signal,
    )
    buy = next(event for event in result.events if event.event_type == "filled_buy")
    sell = next(event for event in result.events if event.event_type == "filled_sell")
    assert buy.decision_date == bars[20].trade_date
    assert buy.execution_date == bars[21].trade_date
    assert buy.quantity % 100 == 0
    assert sell.execution_date == bars[22].trade_date
    assert result.metrics.turnover > 0


def test_nontradable_next_session_rejects_entry_without_future_retry() -> None:
    bars = [_bar(index) for index in range(21)]
    bars.extend([_bar(21, buy_state="limit_up_locked"), _bar(22)])
    result = DailyBacktestEngine().run(
        bars=bars,
        strategy_family="synthetic",
        horizon_sessions=2,
        signal_function=_always_signal,
    )
    assert result.metrics.rejected_orders == 1
    assert not result.trades
    assert result.events[0].reason == "buy_not_tradable"


def test_order_participation_can_block_one_board_lot() -> None:
    assumptions = BacktestAssumptions(maximum_order_participation=0.0001)
    bars = [_bar(index, amount=1_000_000) for index in range(22)]
    result = DailyBacktestEngine(
        assumptions=assumptions,
        universe_rules=UniverseRules(minimum_median_amount_20d_cny=0),
    ).run(
        bars=bars,
        strategy_family="synthetic",
        horizon_sessions=2,
        signal_function=_always_signal,
    )
    assert result.events[-1].reason == "cash_or_liquidity_below_one_lot"


def test_three_strategy_families_and_horizon_guard() -> None:
    base = [_bar(index, close=10, amount=100_000_000) for index in range(20)]
    event = event_attention_signal([*base, _bar(20, close=10.5, amount=200_000_000)], 2)
    momentum = momentum_breakout_signal([*base, _bar(20, close=10.2, amount=120_000_000)], 5)
    falling = [_bar(index, close=10) for index in range(16)]
    falling.extend(
        _bar(index, close=close)
        for index, close in zip(range(16, 20), (9.7, 9.4, 9.2, 9.0), strict=True)
    )
    reversal = reversal_volume_price_signal([*falling, _bar(20, close=9.1, amount=100_000_000)], 10)
    assert event and event.family == "event_attention"
    assert momentum and momentum.family == "momentum_breakout"
    assert reversal and reversal.family == "reversal_volume_price"
    with pytest.raises(ValueError, match="2/5/10"):
        momentum_breakout_signal([*base, _bar(20, close=10.2, amount=120_000_000)], 3)


def test_strategy_and_prediction_identities_are_deterministic() -> None:
    from datetime import UTC, datetime

    created_at = datetime(2026, 7, 27, tzinfo=UTC)
    strategy = freeze_strategy_version(
        family="momentum_breakout",
        universe_version="tactical-universe-v1",
        execution_assumption_version="a-share-daily-execution-v1",
        created_at=created_at,
    )
    signal = momentum_breakout_signal(
        [*[_bar(index) for index in range(20)], _bar(20, close=10.2, amount=120_000_000)],
        5,
    )
    assert signal
    first = build_prediction_batch(
        strategy=strategy,
        feature_snapshot_id="feature-snapshot:fixture",
        as_of=created_at,
        horizon_sessions=5,
        signals=(signal,),
    )
    repeated = build_prediction_batch(
        strategy=strategy,
        feature_snapshot_id="feature-snapshot:fixture",
        as_of=created_at,
        horizon_sessions=5,
        signals=(signal,),
    )
    assert first == repeated
