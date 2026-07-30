"""Immutable contracts for the first WP-0062 production training stage."""

from __future__ import annotations

import math
from datetime import date
from typing import Literal

from pydantic import Field, model_validator

from astramind_mini.contracts import FeatureSnapshot
from astramind_mini.contracts.base import (
    AwareDatetime,
    ContentHash,
    ContractModel,
    Identifier,
    Version,
)

from ...application.identity import research_hash
from ..predictions import MarketPredictionBatch
from ..samples import MembershipKnowledge

ProductionFamily = Literal["industry_heat", "industry_rotation"]
ProductionPipelineState = Literal[
    "production_pipeline_unavailable",
    "training_data_blocked",
    "trained_evidence_insufficient",
    "artifact_incompatible",
]


class ProductionFeatureRow(ContractModel):
    """One label-mature candidate row; eligibility is evaluated again at training time."""

    sample_id: Identifier
    entity_id: Identifier
    feature_at: AwareDatetime
    label_end_at: AwareDatetime
    label_available_at: AwareDatetime
    membership_knowledge: MembershipKnowledge
    horizon_sessions: int = Field(ge=1)
    features: tuple[float | None, ...] = Field(min_length=1)
    label: float

    @model_validator(mode="after")
    def validate_values(self) -> ProductionFeatureRow:
        if self.feature_at >= self.label_end_at:
            raise ValueError("feature time must be before label end")
        if self.label_available_at < self.label_end_at:
            raise ValueError("label cannot be available before label end")
        if not math.isfinite(self.label):
            raise ValueError("training label must be finite")
        if any(value is not None and not math.isfinite(value) for value in self.features):
            raise ValueError("features may be missing but cannot be infinite")
        return self


class ProductionInferenceRow(ContractModel):
    entity_id: Identifier
    feature_at: AwareDatetime
    horizon_sessions: int = Field(ge=1)
    features: tuple[float | None, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_values(self) -> ProductionInferenceRow:
        if any(value is not None and not math.isfinite(value) for value in self.features):
            raise ValueError("features may be missing but cannot be infinite")
        return self


class ProductionFeatureMatrix(ContractModel):
    """Content-addressed features and point-in-time labels from one DataSnapshot."""

    matrix_id: Identifier
    model_family: ProductionFamily
    data_snapshot_id: Identifier
    feature_snapshot: FeatureSnapshot
    definition_version: Version
    as_of: AwareDatetime
    feature_names: tuple[Identifier, ...] = Field(min_length=1)
    rows: tuple[ProductionFeatureRow, ...] = Field(min_length=1)
    inference_rows: tuple[ProductionInferenceRow, ...] = Field(min_length=1)
    content_hash: ContentHash

    @model_validator(mode="after")
    def validate_matrix(self) -> ProductionFeatureMatrix:
        if self.feature_snapshot.data_snapshot_id != self.data_snapshot_id:
            raise ValueError("feature snapshot must bind the matrix DataSnapshot")
        if self.feature_snapshot.as_of != self.as_of:
            raise ValueError("feature snapshot cutoff must match the matrix")
        if self.feature_snapshot.definition_version != self.definition_version:
            raise ValueError("feature definition versions must match")
        if len(set(self.feature_names)) != len(self.feature_names):
            raise ValueError("feature names must be unique and ordered")
        if any(len(row.features) != len(self.feature_names) for row in self.rows):
            raise ValueError("training row width must match feature names")
        if any(len(row.features) != len(self.feature_names) for row in self.inference_rows):
            raise ValueError("inference row width must match feature names")
        sample_ids = [row.sample_id for row in self.rows]
        if len(sample_ids) != len(set(sample_ids)):
            raise ValueError("feature matrix sample identities must be unique")
        digest = research_hash(_matrix_identity(self))
        suffix = digest.removeprefix("sha256:")
        if self.content_hash != digest:
            raise ValueError("feature matrix content hash mismatch")
        if self.matrix_id != f"market-feature-matrix:{suffix}":
            raise ValueError("feature matrix identity mismatch")
        if self.feature_snapshot.content_hash != digest:
            raise ValueError("feature snapshot content hash mismatch")
        if self.feature_snapshot.feature_snapshot_id != f"feature-snapshot:{suffix}":
            raise ValueError("feature snapshot identity mismatch")
        return self


class ProductionPredictionPublication(ContractModel):
    """Read-only unvalidated release metadata around one prediction batch."""

    publication_id: Identifier
    batch: MarketPredictionBatch
    baseline_method_version: Version
    training_cutoff: AwareDatetime
    maturity_cutoff: AwareDatetime
    model_artifact_hash: ContentHash
    feature_content_hash: ContentHash
    evidence_state: Literal["unvalidated"] = "unvalidated"
    broker_actions_allowed: Literal[False] = False
    portfolio_targets_allowed: Literal[False] = False
    order_plans_allowed: Literal[False] = False
    content_hash: ContentHash

    @model_validator(mode="after")
    def validate_publication(self) -> ProductionPredictionPublication:
        if self.batch.evidence_state != "unvalidated":
            raise ValueError("WP-0062 first-stage predictions must remain unvalidated")
        digest = research_hash(_publication_identity(self))
        if self.content_hash != digest:
            raise ValueError("prediction publication content hash mismatch")
        if self.publication_id != "market-prediction-publication:" + digest.removeprefix("sha256:"):
            raise ValueError("prediction publication identity mismatch")
        return self


class ProductionRunResult(ContractModel):
    """Auditable terminal result without activation or execution authority."""

    run_id: Identifier
    request_id: ContentHash
    model_family: str
    data_snapshot_id: Identifier
    scheduled_month: date
    state: ProductionPipelineState
    created_at: AwareDatetime
    reason_codes: tuple[Identifier, ...] = ()
    feature_matrix_id: Identifier | None = None
    manifest_id: Identifier | None = None
    evidence_bundle_id: Identifier | None = None
    prediction_publication_id: Identifier | None = None
    broker_actions_allowed: Literal[False] = False
    portfolio_targets_allowed: Literal[False] = False
    order_plans_allowed: Literal[False] = False
    content_hash: ContentHash

    @model_validator(mode="after")
    def validate_result(self) -> ProductionRunResult:
        references = (
            self.feature_matrix_id,
            self.manifest_id,
            self.evidence_bundle_id,
            self.prediction_publication_id,
        )
        if self.state == "trained_evidence_insufficient":
            if any(value is None for value in references):
                raise ValueError("trained run requires all immutable output references")
            if self.reason_codes != ("supportive_evidence_not_validated",):
                raise ValueError("first-stage trained result must remain evidence-insufficient")
        elif any(value is not None for value in references):
            raise ValueError("blocked run cannot claim published model outputs")
        elif not self.reason_codes:
            raise ValueError("blocked run requires stable reason codes")
        digest = research_hash(_result_identity(self))
        if self.content_hash != digest:
            raise ValueError("production run content hash mismatch")
        if self.run_id != "market-model-run:" + digest.removeprefix("sha256:"):
            raise ValueError("production run identity mismatch")
        return self


def _matrix_identity(matrix: ProductionFeatureMatrix) -> dict[str, object]:
    return {
        "model_family": matrix.model_family,
        "data_snapshot_id": matrix.data_snapshot_id,
        "definition_version": matrix.definition_version,
        "as_of": matrix.as_of,
        "feature_names": matrix.feature_names,
        "rows": matrix.rows,
        "inference_rows": matrix.inference_rows,
    }


def _publication_identity(publication: ProductionPredictionPublication) -> dict[str, object]:
    return publication.model_dump(
        mode="json",
        exclude={"publication_id", "content_hash"},
    )


def _result_identity(result: ProductionRunResult) -> dict[str, object]:
    return result.model_dump(mode="json", exclude={"run_id", "content_hash"})


__all__ = [
    "ProductionFamily",
    "ProductionFeatureMatrix",
    "ProductionFeatureRow",
    "ProductionInferenceRow",
    "ProductionPipelineState",
    "ProductionPredictionPublication",
    "ProductionRunResult",
]
