"""Deterministic thin-waist identities for tactical research artifacts."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import asdict, is_dataclass
from datetime import date, datetime

from pydantic import BaseModel

from astramind_mini.contracts import FeatureSnapshot, PredictionBatch, StrategyVersion

from ..domain.backtest_models import CandidateSignal


def freeze_strategy_version(
    *,
    family: str,
    universe_version: str,
    execution_assumption_version: str,
    created_at: datetime,
    horizon_sessions: int | None = None,
) -> StrategyVersion:
    if horizon_sessions is not None and horizon_sessions not in {2, 5, 10}:
        raise ValueError("策略版本周期只能为 2/5/10 个交易日")
    payload: dict[str, object] = {
        "family": family,
        "parameters": "first-family-defaults-v1",
        "features": "adjusted-market-daily-v1",
        "universe": universe_version,
        "execution": execution_assumption_version,
    }
    if horizon_sessions is not None:
        payload["horizon_sessions"] = horizon_sessions
    digest = _hash(payload)
    logic_suffix = f":h{horizon_sessions}" if horizon_sessions is not None else ""
    feature_version = (
        "tactical-event-and-price-volume-v1"
        if family == "event_attention"
        else "daily-price-volume-v1"
    )
    return StrategyVersion(
        strategy_version_id=f"strategy-version:{digest[7:]}",
        logic_id=f"tactical:{family}{logic_suffix}:v1",
        parameter_set_hash=_hash(
            {"family": family, "defaults": "v1", "horizon_sessions": horizon_sessions}
        ),
        feature_definition_version=feature_version,
        universe_version=universe_version,
        execution_assumption_version=execution_assumption_version,
        code_identity="astramind-mini:wp-0008",
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


def build_feature_snapshot(
    *,
    data_snapshot_id: str,
    as_of: datetime,
    definition_version: str,
    signals: Sequence[CandidateSignal],
) -> FeatureSnapshot:
    payload = {
        "data_snapshot_id": data_snapshot_id,
        "as_of": as_of.isoformat(),
        "definition_version": definition_version,
        "signals": [
            {
                "instrument": item.instrument_id,
                "signal_date": item.signal_date.isoformat(),
                "family": item.family,
                "horizon_sessions": item.horizon_sessions,
                "score": item.score,
                "reasons": item.reasons,
            }
            for item in sorted(signals, key=lambda item: (item.instrument_id, item.signal_date))
        ],
    }
    digest = _hash(payload)
    return FeatureSnapshot(
        feature_snapshot_id=f"feature-snapshot:{digest[7:]}",
        data_snapshot_id=data_snapshot_id,
        as_of=as_of,
        definition_version=definition_version,
        content_hash=digest,
    )


def _hash(value: object) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=_json_default,
    )
    return "sha256:" + hashlib.sha256(payload.encode()).hexdigest()


def _json_default(value: object) -> object:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    raise TypeError(f"无法规范序列化：{type(value).__name__}")


def research_hash(value: object) -> str:
    return _hash(value)


__all__ = [
    "build_feature_snapshot",
    "build_prediction_batch",
    "freeze_strategy_version",
    "research_hash",
]
