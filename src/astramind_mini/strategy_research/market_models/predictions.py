"""Immutable prediction batches for read-only market models."""

from __future__ import annotations

import math

from pydantic import Field, model_validator

from astramind_mini.contracts.base import (
    AwareDatetime,
    ContentHash,
    ContractModel,
    Identifier,
)

from ..application.identity import research_hash
from .contracts import EvidenceState, MarketModelFamily


class RegressionPrediction(ContractModel):
    entity_id: Identifier
    horizon_sessions: int = Field(ge=1)
    predicted_value: float
    standardized_value: float | None = None

    @model_validator(mode="after")
    def validate_values(self) -> RegressionPrediction:
        values = (self.predicted_value, self.standardized_value)
        if any(value is not None and not math.isfinite(value) for value in values):
            raise ValueError("regression predictions must be finite")
        return self


class ClassProbability(ContractModel):
    label: Identifier
    probability: float = Field(ge=0.0, le=1.0)


class ClassificationPrediction(ContractModel):
    entity_id: Identifier
    horizon_sessions: int = Field(ge=1)
    predicted_label: Identifier
    probabilities: tuple[ClassProbability, ...] = Field(min_length=2)

    @model_validator(mode="after")
    def validate_probabilities(self) -> ClassificationPrediction:
        labels = [item.label for item in self.probabilities]
        if len(set(labels)) != len(labels):
            raise ValueError("classification probability labels must be unique")
        if self.predicted_label not in labels:
            raise ValueError("predicted class must exist in probabilities")
        if not math.isclose(
            sum(item.probability for item in self.probabilities),
            1.0,
            abs_tol=1e-9,
        ):
            raise ValueError("classification probabilities must sum to one")
        return self


class MarketPredictionBatch(ContractModel):
    prediction_batch_id: Identifier
    model_family: MarketModelFamily
    manifest_id: Identifier
    data_snapshot_id: Identifier
    feature_snapshot_id: Identifier
    as_of: AwareDatetime
    horizons: tuple[int, ...] = Field(min_length=1)
    regressions: tuple[RegressionPrediction, ...] = ()
    classifications: tuple[ClassificationPrediction, ...] = ()
    evidence_state: EvidenceState
    content_hash: ContentHash
    broker_actions_allowed: bool = False

    @model_validator(mode="after")
    def validate_batch(self) -> MarketPredictionBatch:
        if bool(self.regressions) == bool(self.classifications):
            raise ValueError("prediction batch must contain exactly one prediction kind")
        if len(set(self.horizons)) != len(self.horizons):
            raise ValueError("prediction horizons must be unique")
        records = self.regressions or self.classifications
        if {item.horizon_sessions for item in records} != set(self.horizons):
            raise ValueError("record horizons must match batch horizons")
        if self.broker_actions_allowed:
            raise ValueError("market prediction batches cannot allow broker actions")
        identity = _batch_identity(self)
        digest = research_hash(identity)
        if self.content_hash != digest:
            raise ValueError("prediction batch content hash mismatch")
        if self.prediction_batch_id != "market-prediction:" + digest.removeprefix("sha256:"):
            raise ValueError("prediction batch identity mismatch")
        return self


def freeze_prediction_batch(
    *,
    model_family: MarketModelFamily,
    manifest_id: str,
    data_snapshot_id: str,
    feature_snapshot_id: str,
    as_of: AwareDatetime,
    horizons: tuple[int, ...],
    evidence_state: EvidenceState,
    regressions: tuple[RegressionPrediction, ...] = (),
    classifications: tuple[ClassificationPrediction, ...] = (),
) -> MarketPredictionBatch:
    provisional = MarketPredictionBatch.model_construct(
        prediction_batch_id="market-prediction:pending",
        model_family=model_family,
        manifest_id=manifest_id,
        data_snapshot_id=data_snapshot_id,
        feature_snapshot_id=feature_snapshot_id,
        as_of=as_of,
        horizons=horizons,
        regressions=regressions,
        classifications=classifications,
        evidence_state=evidence_state,
        content_hash="sha256:" + "0" * 64,
        broker_actions_allowed=False,
    )
    digest = research_hash(_batch_identity(provisional))
    return MarketPredictionBatch(
        **provisional.model_dump(
            exclude={"prediction_batch_id", "content_hash"},
        ),
        prediction_batch_id="market-prediction:" + digest.removeprefix("sha256:"),
        content_hash=digest,
    )


def _batch_identity(batch: MarketPredictionBatch) -> dict[str, object]:
    return batch.model_dump(
        mode="json",
        exclude={"prediction_batch_id", "content_hash"},
    )


__all__ = [
    "ClassProbability",
    "ClassificationPrediction",
    "MarketPredictionBatch",
    "RegressionPrediction",
    "freeze_prediction_batch",
]
