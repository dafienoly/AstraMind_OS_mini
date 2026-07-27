"""Deterministic thin-waist identities for tactical research artifacts."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from datetime import datetime

from astramind_mini.contracts import PredictionBatch, StrategyVersion

from ..domain.backtest_models import CandidateSignal


def freeze_strategy_version(
    *,
    family: str,
    universe_version: str,
    execution_assumption_version: str,
    created_at: datetime,
) -> StrategyVersion:
    payload = {
        "family": family,
        "parameters": "first-family-defaults-v1",
        "features": "adjusted-market-daily-v1",
        "universe": universe_version,
        "execution": execution_assumption_version,
    }
    digest = _hash(payload)
    return StrategyVersion(
        strategy_version_id=f"strategy-version:{digest[7:]}",
        logic_id=f"tactical:{family}:v1",
        parameter_set_hash=_hash({"family": family, "defaults": "v1"}),
        feature_definition_version="daily-price-volume-v1",
        universe_version=universe_version,
        execution_assumption_version=execution_assumption_version,
        code_identity="astramind-mini:wp-0005",
        created_at=created_at,
    )


def build_prediction_batch(
    *,
    strategy: StrategyVersion,
    feature_snapshot_id: str,
    as_of: datetime,
    horizon_sessions: int,
    signals: Sequence[CandidateSignal],
) -> PredictionBatch:
    payload = {
        "strategy": strategy.strategy_version_id,
        "feature_snapshot": feature_snapshot_id,
        "as_of": as_of.isoformat(),
        "horizon": horizon_sessions,
        "signals": [
            {
                "instrument": item.instrument_id,
                "signal_date": item.signal_date.isoformat(),
                "score": item.score,
                "reasons": item.reasons,
            }
            for item in sorted(signals, key=lambda item: (item.instrument_id, item.signal_date))
        ],
    }
    digest = _hash(payload)
    return PredictionBatch(
        prediction_batch_id=f"prediction-batch:{digest[7:]}",
        strategy_version_id=strategy.strategy_version_id,
        feature_snapshot_id=feature_snapshot_id,
        as_of=as_of,
        horizon_sessions=horizon_sessions,
        content_hash=digest,
    )


def _hash(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(payload.encode()).hexdigest()


__all__ = ["build_prediction_batch", "freeze_strategy_version"]
