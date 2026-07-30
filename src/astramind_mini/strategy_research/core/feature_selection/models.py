"""Immutable evidence and manifest contracts for fold-internal feature selection."""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from statistics import median
from typing import Literal

from pydantic import Field, model_validator

from astramind_mini.contracts.base import ContentHash, ContractModel, Identifier

from ...application.identity import research_hash
from ..labels import CoreLabelHorizon
from .coverage import CoreFoldCoverageEvidence
from .plan import CoreSelectionFold
from .priors import STAGE_P_PRIORS_CONTENT_HASH, STAGE_P_TOKENIZER_RULES_HASH
from .turnover import CoreTurnoverTransitionEvidence


class CoreSelectionReason(StrEnum):
    SELECTED = "selected"
    COVERAGE_GATE_FAILED = "coverage_gate_failed"
    SUBFOLD_SAMPLE_INSUFFICIENT = "subfold_sample_insufficient"
    P_VALUE_UNAVAILABLE = "p_value_unavailable"
    BH_REJECTED = "bh_rejected"
    CLUSTER_REDUNDANT = "cluster_redundant"


class CoreCorrelationStatus(StrEnum):
    AVAILABLE = "available"
    CORRELATION_EVIDENCE_INSUFFICIENT = "correlation_evidence_insufficient"


class CoreSelectionSpec(ContractModel):
    spec_version: Literal["core-feature-selection-v1"] = "core-feature-selection-v1"
    allowed_horizons: tuple[CoreLabelHorizon, CoreLabelHorizon] = (
        CoreLabelHorizon.H20,
        CoreLabelHorizon.H60,
    )
    bootstrap_block_length: Literal[20] = 20
    bootstrap_replicates: Literal[10_000] = 10_000
    bh_fdr: float = 0.10
    minimum_subfold_valid_rankic: Literal[60] = 60
    correlation_minimum_daily_pairs: Literal[5] = 5
    correlation_minimum_valid_dates: Literal[60] = 60
    correlation_cluster_absolute_threshold: float = 0.85
    complete_linkage_maximum_distance: float = 0.15
    turnover_minimum_common_instruments: Literal[5] = 5
    turnover_minimum_valid_transitions: Literal[60] = 60

    @model_validator(mode="after")
    def validate_fixed_v1(self) -> CoreSelectionSpec:
        if (
            self.spec_version != "core-feature-selection-v1"
            or self.allowed_horizons != (CoreLabelHorizon.H20, CoreLabelHorizon.H60)
            or self.bootstrap_block_length != 20
            or self.bootstrap_replicates != 10_000
            or self.bh_fdr != 0.10
            or self.minimum_subfold_valid_rankic != 60
            or self.correlation_minimum_daily_pairs != 5
            or self.correlation_minimum_valid_dates != 60
            or self.correlation_cluster_absolute_threshold != 0.85
            or self.complete_linkage_maximum_distance != 0.15
            or self.turnover_minimum_common_instruments != 5
            or self.turnover_minimum_valid_transitions != 60
        ):
            raise ValueError("core-feature-selection-v1 constants are immutable")
        return self


class CoreDailyRankICEvidence(ContractModel):
    decision_date: date
    pair_count: int = Field(ge=0)
    rank_ic: float | None = Field(default=None, ge=-1.0, le=1.0)
    signed_rank_ic: float | None = Field(default=None, ge=-1.0, le=1.0)


class CoreSubfoldRankICEvidence(ContractModel):
    subfold_id: Identifier
    valid_count: int = Field(ge=0)
    signed_mean_rank_ic: float | None = Field(default=None, ge=-1.0, le=1.0)
    sample_sufficient: bool


class CoreFeatureSelectionEvidence(ContractModel):
    feature_key: Identifier
    feature_id: Identifier
    definition_version: Identifier
    canonical_order: int = Field(gt=0)
    expected_direction: Literal[-1, 1]
    complexity: int = Field(ge=1)
    coverage: CoreFoldCoverageEvidence
    daily_rank_ic: tuple[CoreDailyRankICEvidence, ...] = Field(min_length=1)
    subfolds: tuple[
        CoreSubfoldRankICEvidence,
        CoreSubfoldRankICEvidence,
        CoreSubfoldRankICEvidence,
    ]
    direction_consistent: bool
    signed_mean_rank_ic: float | None = Field(default=None, ge=-1.0, le=1.0)
    bootstrap_seed: int | None = Field(default=None, ge=0)
    bootstrap_p_value: float | None = Field(default=None, ge=0.0, le=1.0)
    selection_eligible: bool
    bh_rank: int | None = Field(default=None, ge=1)
    bh_threshold: float | None = Field(default=None, ge=0.0, le=1.0)
    bh_passed: bool
    coverage_mean: float | None = Field(default=None, ge=0.0, le=1.0)
    turnover: float | None = Field(default=None, ge=0.0, le=1.0)
    turnover_valid_transitions: int = Field(ge=0)
    turnover_transitions: tuple[CoreTurnoverTransitionEvidence, ...]
    stability: float | None = Field(default=None, ge=0.0, le=1.0)
    reason_code: CoreSelectionReason

    @model_validator(mode="after")
    def validate_turnover(self) -> CoreFeatureSelectionEvidence:
        valid = tuple(
            float(item.turnover_ratio)
            for item in self.turnover_transitions
            if item.turnover_ratio is not None
        )
        expected = float(median(valid)) if len(valid) >= 60 else None
        if self.turnover_valid_transitions != len(valid) or self.turnover != expected:
            raise ValueError("feature turnover aggregate does not match transition evidence")
        return self


class CorePairCorrelationEvidence(ContractModel):
    left_feature_key: Identifier
    right_feature_key: Identifier
    valid_date_count: int = Field(ge=0)
    median_daily_spearman: float | None = Field(default=None, ge=-1.0, le=1.0)
    distance: float | None = Field(default=None, ge=0.0, le=1.0)
    status: CoreCorrelationStatus


class CoreSelectionCluster(ContractModel):
    members: tuple[Identifier, ...] = Field(min_length=1)
    representative: Identifier

    @model_validator(mode="after")
    def validate_members(self) -> CoreSelectionCluster:
        if self.members != tuple(sorted(set(self.members))):
            raise ValueError("selection cluster members must be unique and ordered")
        if self.representative not in self.members:
            raise ValueError("selection cluster representative must be a member")
        return self


class CoreLabelBatchReference(ContractModel):
    decision_date: date
    batch_id: Identifier
    content_hash: ContentHash
    universe_content_hash: ContentHash


class CoreProcessedDayReference(ContractModel):
    decision_date: date
    processed_envelope_id: Identifier
    processed_envelope_content_hash: ContentHash
    universe_content_hash: ContentHash


class CoreFeatureSelectionManifest(ContractModel):
    manifest_id: Identifier
    content_hash: ContentHash
    package_id: Identifier
    horizon: CoreLabelHorizon
    fold: CoreSelectionFold
    panel_manifest_id: Identifier
    panel_content_hash: ContentHash
    prior_content_hash: ContentHash
    prior_tokenizer_rules_hash: ContentHash
    selection_spec: CoreSelectionSpec
    selection_spec_hash: ContentHash
    processed_days: tuple[CoreProcessedDayReference, ...] = Field(min_length=1)
    label_batches: tuple[CoreLabelBatchReference, ...] = Field(min_length=1)
    feature_order: tuple[Identifier, ...] = Field(min_length=1)
    feature_evidence: tuple[CoreFeatureSelectionEvidence, ...] = Field(min_length=1)
    pair_correlations: tuple[CorePairCorrelationEvidence, ...]
    clusters: tuple[CoreSelectionCluster, ...]
    selected_feature_keys: tuple[Identifier, ...]
    selected_feature_ids: tuple[Identifier, ...]

    @model_validator(mode="after")
    def validate_identity(self) -> CoreFeatureSelectionManifest:
        CoreSelectionSpec.model_validate(self.selection_spec.model_dump())
        if self.horizon not in {
            CoreLabelHorizon.H20,
            CoreLabelHorizon.H60,
        }:
            raise ValueError("D1/D3/D5 cannot form a production selection manifest")
        if (
            self.prior_content_hash != STAGE_P_PRIORS_CONTENT_HASH
            or self.prior_tokenizer_rules_hash != STAGE_P_TOKENIZER_RULES_HASH
        ):
            raise ValueError("selection manifest requires integrated Stage P identities")
        if self.selection_spec_hash != research_hash(self.selection_spec):
            raise ValueError("selection spec hash mismatch")
        if tuple(item.feature_id for item in self.feature_evidence) != self.feature_order:
            raise ValueError("feature evidence must preserve canonical package order")
        evidence_keys = tuple(item.feature_key for item in self.feature_evidence)
        if (
            len(set(self.feature_order)) != len(self.feature_order)
            or len(set(evidence_keys)) != len(evidence_keys)
            or len(set(self.selected_feature_keys)) != len(self.selected_feature_keys)
        ):
            raise ValueError("selection feature identities must be unique")
        if (
            tuple(item.decision_date for item in self.processed_days) != self.fold.decision_dates
            or tuple(item.decision_date for item in self.label_batches) != self.fold.decision_dates
            or tuple(item.universe_content_hash for item in self.processed_days)
            != tuple(item.universe_content_hash for item in self.label_batches)
        ):
            raise ValueError("selection daily processed/label lineage must match the fold")
        from .manifest_validation import validate_selection_evidence

        validate_selection_evidence(self)
        expected_hash = research_hash(_selection_payload(self))
        expected_id = f"core-selection:{expected_hash.removeprefix('sha256:')}"
        if self.content_hash != expected_hash or self.manifest_id != expected_id:
            raise ValueError("selection manifest canonical identity mismatch")
        return self


def _selection_payload(manifest: CoreFeatureSelectionManifest) -> dict[str, object]:
    return {
        "schema": "core-feature-selection-manifest-v1",
        **{
            key: value
            for key, value in manifest.model_dump().items()
            if key not in {"manifest_id", "content_hash"}
        },
    }


__all__ = [
    "CoreCorrelationStatus",
    "CoreDailyRankICEvidence",
    "CoreFeatureSelectionEvidence",
    "CoreFeatureSelectionManifest",
    "CoreLabelBatchReference",
    "CorePairCorrelationEvidence",
    "CoreProcessedDayReference",
    "CoreSelectionCluster",
    "CoreSelectionReason",
    "CoreSelectionSpec",
    "CoreSubfoldRankICEvidence",
]
