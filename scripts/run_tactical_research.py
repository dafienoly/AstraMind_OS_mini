"""Bounded production-snapshot plumbing smoke for the first tactical families."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, date, datetime, time
from pathlib import Path

from astramind_mini.strategy_research.adapters.snapshot_market import SnapshotMarketReader
from astramind_mini.strategy_research.application.backtest import DailyBacktestEngine
from astramind_mini.strategy_research.application.identity import freeze_strategy_version
from astramind_mini.strategy_research.application.strategies import (
    event_attention_signal,
    momentum_breakout_signal,
    reversal_volume_price_signal,
)
from astramind_mini.strategy_research.domain.backtest_models import UniverseRules

STRATEGIES = {
    "event_attention": event_attention_signal,
    "momentum_breakout": momentum_breakout_signal,
    "reversal_volume_price": reversal_volume_price_signal,
}


def run(args: argparse.Namespace) -> Path:
    reader = SnapshotMarketReader(args.data_root, args.snapshot_id)
    rules = UniverseRules()
    instruments = reader.eligible_instruments(as_of=args.as_of, rules=rules, limit=args.limit)
    bars = reader.load_bars(
        instruments=instruments,
        start_date=args.start_date,
        end_date=args.as_of,
    )
    as_of = datetime.combine(args.as_of, time(15), tzinfo=UTC)
    engine = DailyBacktestEngine(universe_rules=rules)
    results: list[dict[str, object]] = []
    for family, signal_function in STRATEGIES.items():
        strategy = freeze_strategy_version(
            family=family,
            universe_version=rules.version,
            execution_assumption_version="a-share-daily-execution-v1",
            created_at=as_of,
        )
        for horizon in (2, 5, 10):
            backtest = engine.run(
                bars=bars,
                strategy_family=family,
                horizon_sessions=horizon,
                signal_function=signal_function,
            )
            results.append(
                {
                    "strategy_version_id": strategy.strategy_version_id,
                    "family": family,
                    "horizon_sessions": horizon,
                    "closed_trades": backtest.metrics.closed_trades,
                    "rejected_orders": backtest.metrics.rejected_orders,
                    "total_return": backtest.metrics.total_return,
                    "max_drawdown": backtest.metrics.max_drawdown,
                }
            )
    payload = {
        "purpose": "bounded_plumbing_smoke_not_strategy_evidence",
        "snapshot_id": args.snapshot_id,
        "selection_as_of": args.as_of.isoformat(),
        "start_date": args.start_date.isoformat(),
        "instrument_count": len(instruments),
        "results": results,
    }
    output = Path(args.output) / f"{args.as_of.isoformat()}-tactical-smoke.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2),
        encoding="utf-8",
    )
    return output


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot-id", required=True)
    parser.add_argument("--data-root", type=Path, default=Path("var/data"))
    parser.add_argument("--start-date", type=date.fromisoformat, default=date(2025, 1, 1))
    parser.add_argument("--as-of", type=date.fromisoformat, required=True)
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--output", type=Path, default=Path("var/research"))
    args = parser.parse_args()
    path = run(args)
    print(f"战术研究贯通证据：{path}")
    print("注意：这是小样本管线证明，不是策略有效性或封存期结论。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
