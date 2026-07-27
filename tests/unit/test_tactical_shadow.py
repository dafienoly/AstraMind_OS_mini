"""Proof for tactical targets and broker-free Shadow execution."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

from astramind_mini.portfolio_risk.application.tactical_target import build_tactical_target
from astramind_mini.trading_execution.adapters.shadow_ledger import ShadowLedger
from astramind_mini.trading_execution.application.shadow import (
    build_shadow_order_plan,
    project_shadow_portfolio,
    simulate_shadow,
)
from astramind_mini.trading_execution.domain.shadow import ShadowPortfolioState, ShadowQuote


def test_tactical_target_is_cash_valid_and_limited_to_two_positions() -> None:
    now = datetime(2026, 7, 27, 8, tzinfo=UTC)
    problem, result, target, details = build_tactical_target(
        prediction_batch_ids=("prediction:a",),
        ranked_candidates=(("AAA.SZ", 10.0), ("BBB.SH", 20.0), ("CCC.BJ", 5.0)),
        as_of=now,
    )
    assert len(details.holdings) == 2
    assert sum(item.weight for item in details.holdings) + details.cash_weight == 1
    assert result.optimization_problem_id == problem.optimization_problem_id
    assert target.optimization_result_id == result.optimization_result_id


def test_shadow_plan_uses_common_contract_and_records_partial_and_stale_events() -> None:
    now = datetime(2026, 7, 27, 8, tzinfo=UTC)
    _, _, target, details = build_tactical_target(
        prediction_batch_ids=("prediction:a",),
        ranked_candidates=(("AAA.SZ", 10.0), ("BBB.SH", 20.0)),
        as_of=now,
    )
    plan, lines = build_shadow_order_plan(target, details, current_shares={}, created_at=now)
    assert plan.execution_mode == "shadow"
    quotes = {
        "AAA.SZ": ShadowQuote("AAA.SZ", now, 10.1, 1_000),
        "BBB.SH": ShadowQuote("BBB.SH", now - timedelta(minutes=1), 20.1, 2_000),
    }
    fills, events = simulate_shadow(plan, lines, quotes, now=now)
    assert {fill.status for fill in fills} == {"partial", "rejected"}
    assert {fill.reason for fill in fills} == {
        "bounded_by_available_quantity",
        "stale_quote",
    }
    assert all(event.order_plan_id == plan.order_plan_id for event in events)
    projected = project_shadow_portfolio(ShadowPortfolioState(50_000), fills)
    assert projected.cash_cny >= 0
    assert len(projected.positions) == 1


def test_shadow_ledger_recovers_and_is_idempotent(tmp_path: Path) -> None:
    now = datetime(2026, 7, 27, 8, tzinfo=UTC)
    _, _, target, details = build_tactical_target(
        prediction_batch_ids=("prediction:a",),
        ranked_candidates=(("AAA.SZ", 10.0),),
        as_of=now,
    )
    plan, lines = build_shadow_order_plan(target, details, current_shares={}, created_at=now)
    _, events = simulate_shadow(
        plan,
        lines,
        {"AAA.SZ": ShadowQuote("AAA.SZ", now, 10.1, 10_000)},
        now=now,
    )
    database = tmp_path / "shadow.sqlite3"
    ledger = ShadowLedger(database)
    ledger.migrate()
    ledger.append(events[0], {"filled": 4_500})
    ledger.append(events[0], {"filled": 4_500})
    restarted = ShadowLedger(database)
    restarted.migrate()
    assert restarted.journal_mode() == "wal"
    assert restarted.events_for(plan.order_plan_id) == ({"filled": 4500},)
