"""Run the explicit, long REQ-0005 sealed replay outside default checks."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from datetime import UTC, date, datetime
from pathlib import Path

from astramind_mini.strategy_research.adapters import DuckDBSealedReplaySource
from astramind_mini.strategy_research.application import (
    SealedReplayRunner,
    build_evidence_bundle,
)
from astramind_mini.strategy_research.application.identity import (
    freeze_strategy_version,
    research_hash,
)

_DEVELOPMENT_CUTOFF = date(2022, 12, 31)
_SEALED_START = date(2023, 1, 1)
_SEALED_END = date(2025, 12, 31)
_FAMILIES = ("event_attention", "momentum_breakout", "reversal_volume_price")
_HORIZONS = (2, 5, 10)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot-id", required=True)
    parser.add_argument("--data-root", type=Path, default=Path("var/data"))
    parser.add_argument("--output-root", type=Path, default=Path("var/research/sealed"))
    arguments = parser.parse_args()

    created_at = datetime.now(UTC)
    source = DuckDBSealedReplaySource(arguments.data_root, arguments.snapshot_id)
    runner = SealedReplayRunner(source)
    strategies = {}
    results = {}
    for family in _FAMILIES:
        for horizon in _HORIZONS:
            key = (family, horizon)
            strategies[key] = freeze_strategy_version(
                family=family,
                horizon_sessions=horizon,
                universe_version="tactical-universe-v1",
                execution_assumption_version="a-share-daily-execution-v1",
                created_at=created_at,
            )
            print(f"运行封存回放：{family} / {horizon} sessions", flush=True)
            results[key] = runner.run(
                family=family,
                horizon_sessions=horizon,
                start_date=_SEALED_START,
                end_date=_SEALED_END,
            )
    candidate_set_id = "candidate-set:" + research_hash(
        {
            f"{family}:{horizon}": strategy.strategy_version_id
            for (family, horizon), strategy in sorted(strategies.items())
        }
    ).removeprefix("sha256:")
    bundle = build_evidence_bundle(
        data_snapshot_id=arguments.snapshot_id,
        frozen_candidate_set_id=candidate_set_id,
        development_cutoff=_DEVELOPMENT_CUTOFF,
        sealed_start=_SEALED_START,
        sealed_end=_SEALED_END,
        candidates=strategies,
        results=results,
        created_at=created_at,
        limitations=(
            "historical_period_cannot_be_retroactively_proven_unseen",
            "historical_industry_membership_not_available",
            "market_regime_breakdown_pending_req_0008",
        ),
    )
    directory = arguments.output_root / bundle.bundle_id.rsplit(":", 1)[-1]
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "evidence-bundle.json").write_text(
        bundle.model_dump_json(indent=2), encoding="utf-8"
    )
    for (family, horizon), result in sorted(results.items()):
        (directory / f"{family}-{horizon}.json").write_text(
            json.dumps(
                asdict(result),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                default=_json_default,
            ),
            encoding="utf-8",
        )
    print(
        json.dumps(
            {
                "bundle_id": bundle.bundle_id,
                "data_snapshot_id": bundle.data_snapshot_id,
                "evidence_count": len(bundle.evidence),
                "broker_enabled": bundle.broker_enabled,
                "output_directory": str(directory),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


def _json_default(value: object) -> object:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    raise TypeError(f"无法序列化封存结果：{type(value).__name__}")


if __name__ == "__main__":
    raise SystemExit(main())
