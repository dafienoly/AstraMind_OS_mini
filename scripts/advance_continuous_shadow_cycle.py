"""Advance an existing continuous Shadow cycle with an exact daily snapshot."""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
from typing import cast

from astramind_mini.config import Settings
from astramind_mini.contracts import PortfolioTarget, PredictionBatch
from astramind_mini.data.public import SnapshotShadowMarketReader
from astramind_mini.trading_execution.adapters import ContinuousShadowStore
from astramind_mini.trading_execution.application import ShadowCycleCompletionService
from astramind_mini.trading_execution.contracts import (
    ContinuousShadowCycle,
    ContinuousShadowOrderPlan,
    ShadowCycleCheckpoint,
    ShadowCycleResult,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cycle-artifact", required=True, type=Path)
    parser.add_argument("--snapshot-id", required=True)
    parser.add_argument("--through-date", required=True, type=date.fromisoformat)
    parser.add_argument("--data-root", type=Path, default=Path("var/data"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    artifact = _artifact(args.cycle_artifact)
    cycle = ContinuousShadowCycle.model_validate_json(json.dumps(artifact["cycle"]))
    entry_plan = ContinuousShadowOrderPlan.model_validate_json(json.dumps(artifact["order_plan"]))
    target = PortfolioTarget.model_validate_json(json.dumps(artifact["portfolio_target"]))
    prediction = PredictionBatch.model_validate_json(json.dumps(artifact["prediction_batch"]))
    details = cast(dict[str, object], artifact["target_details"])
    capital_cny = float(cast(float | str, details["capital_cny"]))
    if args.through_date < cycle.scheduled_execution_date:
        _waiting(cycle, args.through_date)
        return 0

    reader = SnapshotShadowMarketReader(args.data_root, args.snapshot_id)
    settings = Settings()
    store = ContinuousShadowStore(settings.shadow_db_path)
    store.migrate()
    service = ShadowCycleCompletionService(store)
    latest = store.latest_checkpoint(cycle.cycle_id)
    start_date = (
        cycle.scheduled_execution_date
        if latest is None
        else date.fromordinal(latest.trading_date.toordinal() + 1)
    )
    trading_dates = reader.trading_dates(start_date=start_date, end_date=args.through_date)
    if not trading_dates:
        _print_current(cycle, latest)
        return 0

    instruments = tuple(sorted(item.instrument_id for item in entry_plan.lines))
    terminal = store.read_result_for_cycle(cycle.cycle_id)
    for trading_date in trading_dates:
        observations = reader.observations(
            instruments=instruments,
            trade_date=trading_date,
        )
        checkpoint, terminal = service.advance_session(
            cycle=cycle,
            target=target,
            entry_plan=entry_plan,
            observations=observations,
            trading_date=trading_date,
            horizon_sessions=prediction.horizon_sessions,
            capital_cny=capital_cny,
        )
        print(
            f"trading_date={trading_date.isoformat()} phase={checkpoint.phase} "
            f"status={checkpoint.status} sessions_elapsed={checkpoint.sessions_elapsed}"
        )
        if terminal is not None:
            break
    _print_result(cycle, store.latest_checkpoint(cycle.cycle_id), terminal)
    return 0


def _artifact(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("持续 Shadow 周期制品必须是 JSON 对象")
    return cast(dict[str, object], payload)


def _waiting(cycle: ContinuousShadowCycle, through_date: date) -> None:
    print(f"continuous_shadow_cycle_id={cycle.cycle_id}")
    print("status=waiting_next_open")
    print(f"through_date={through_date.isoformat()}")
    print(f"scheduled_execution_date={cycle.scheduled_execution_date.isoformat()}")
    print("broker_actions_allowed=false")


def _print_current(
    cycle: ContinuousShadowCycle,
    latest: ShadowCycleCheckpoint | None,
) -> None:
    print(f"continuous_shadow_cycle_id={cycle.cycle_id}")
    print(f"status={getattr(latest, 'status', 'waiting_next_open')}")
    print("new_checkpoint_count=0")
    print("broker_actions_allowed=false")


def _print_result(
    cycle: ContinuousShadowCycle,
    latest: ShadowCycleCheckpoint | None,
    result: ShadowCycleResult | None,
) -> None:
    print(f"continuous_shadow_cycle_id={cycle.cycle_id}")
    print(f"status={getattr(latest, 'status', 'waiting_next_open')}")
    if result is not None:
        print(f"shadow_cycle_result_id={result.result_id}")
        print(f"total_return={result.total_return}")
    print("broker_actions_allowed=false")


if __name__ == "__main__":
    raise SystemExit(main())
