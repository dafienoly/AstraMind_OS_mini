"""Run a fully local synthetic Shadow order-plan lifecycle."""

from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from astramind_mini.portfolio_risk.application.tactical_target import build_tactical_target
from astramind_mini.trading_execution.adapters.shadow_ledger import ShadowLedger
from astramind_mini.trading_execution.application.shadow import (
    build_shadow_order_plan,
    project_shadow_portfolio,
    simulate_shadow,
)
from astramind_mini.trading_execution.domain.shadow import ShadowPortfolioState, ShadowQuote


def main() -> int:
    now = datetime.now(UTC)
    _, _, target, details = build_tactical_target(
        prediction_batch_ids=("prediction-batch:synthetic-shadow-smoke",),
        ranked_candidates=(("SYNTHETIC-A.SZ", 10.0), ("SYNTHETIC-B.SH", 20.0)),
        as_of=now,
    )
    plan, lines = build_shadow_order_plan(
        target,
        details,
        current_shares={},
        created_at=now,
    )
    quotes = {
        "SYNTHETIC-A.SZ": ShadowQuote("SYNTHETIC-A.SZ", now, 10.02, 10_000),
        "SYNTHETIC-B.SH": ShadowQuote("SYNTHETIC-B.SH", now, 20.04, 600),
    }
    fills, events = simulate_shadow(plan, lines, quotes, now=now)
    portfolio = project_shadow_portfolio(ShadowPortfolioState(50_000), fills)
    ledger = ShadowLedger(Path("var/control/shadow.sqlite3"))
    ledger.migrate()
    for fill, event in zip(fills, events, strict=True):
        ledger.append(event, asdict(fill))
    print(
        f"Shadow plan={plan.order_plan_id} events={len(events)} "
        f"states={','.join(fill.status for fill in fills)} "
        f"positions={len(portfolio.positions)} cash_nonnegative={portfolio.cash_cny >= 0} "
        "broker_side_effect=false"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
