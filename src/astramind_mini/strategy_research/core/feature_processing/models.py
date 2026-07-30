"""Immutable daily processed-feature contracts."""

from __future__ import annotations

import math
from datetime import date
from enum import StrEnum
from typing import Literal

from pydantic import Field, model_validator

from astramind_mini.contracts.base import (
    ContentHash,
    ContractModel,
    Identifier,
    Version,
)

from ...application.identity import research_hash
from ..feature_values import CoreImputationSource, FeatureAvailabilityState


class CoreCrossSectionStatus(StrEnum):
    READY = "ready"
    ZERO_SCALE = "zero_scale"
    NO_OBSERVED = "no_observed_cross_section"


class CoreNeutralizationStatus(StrEnum):
    AVAILABLE = "available"
    CONTROLS_MISSING = "controls_missing"
    INSUFFICIENT_SAMPLE = "insufficient_sample"
    RANK_DEFICIENT = "rank_deficient"


class CoreProcessingSpec(ContractModel):
    spec_version: Literal["core-feature-processing-v1"] = "core-feature-processing-v1"
    mad_consistency_constant: float = 1.4826
    winsor_mad_multiple: float = 5.0
    industry_imputation_minimum_observed: Literal[10] = 10
    coverage_date_threshold: float = 0.8
    coverage_passing_date_ratio: float = 0.9
    neutralization_minimum_n_per_parameter: Literal[5] = 5
    neutralization_controls: tuple[str, ...] = (
        "intercept",
        "log_float_market_cap",
        "sw_l1_one_hot_lexical_baseline",
    )
    non_finite_policy: Literal["protected_raw_envelope_rejects"] = "protected_raw_envelope_rejects"

    @model_validator(mode="after")
    def validate_fixed_v1(self) -> CoreProcessingSpec:
        if (
            self.spec_version != "core-feature-processing-v1"
            or self.mad_consistency_constant != 1.4826
            or self.winsor_mad_multiple != 5.0
            or self.industry_imputation_minimum_observed != 10
            or self.coverage_date_threshold != 0.8
            or self.coverage_passing_date_ratio != 0.9
            or self.neutralization_minimum_n_per_parameter != 5
            or self.neutralization_controls
            != (
                "intercept",
                "log_float_market_cap",
                "sw_l1_one_hot_lexical_baseline",
            )
            or self.non_finite_policy != "protected_raw_envelope_rejects"
        ):
            raise ValueError("core-feature-processing-v1 constants are immutable")
        return self


class CoreCrossSectionEvidence(ContractModel):
    feature_id: Identifier
    feature_definition_version: Version
    observed_count: int = Field(ge=0)
    missing_count: int = Field(ge=0)
    not_applicable_count: int = Field(ge=0)
    applicable_count: int = Field(ge=0)
    coverage: float | None = Field(default=None, ge=0.0, le=1.0)
    median_raw: float | None = None
    mad_scale: float | None = Field(default=None, ge=0.0)
    winsor_lower: float | None = None
    winsor_upper: float | None = None
    status: CoreCrossSectionStatus
    neutralization_status: CoreNeutralizationStatus
    neutralization_sample_count: int = Field(ge=0)
    neutralization_parameter_count: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_counts(self) -> CoreCrossSectionEvidence:
        if any(
            item is not None and not math.isfinite(item)
            for item in (
                self.coverage,
                self.median_raw,
                self.mad_scale,
                self.winsor_lower,
                self.winsor_upper,
            )
        ):
            raise ValueError("cross-section evidence values must be finite")
        if self.applicable_count != self.observed_count + self.missing_count:
            raise ValueError("applicable count excludes only not_applicable")
        expected = self.observed_count / self.applicable_count if self.applicable_count else None
        if self.coverage != expected:
            raise ValueError("cross-section applicable coverage mismatch")
        if self.status == CoreCrossSectionStatus.NO_OBSERVED and any(
            item is not None
            for item in (
                self.median_raw,
                self.mad_scale,
                self.winsor_lower,
                self.winsor_upper,
            )
        ):
            raise ValueError("no-observed evidence cannot carry robust statistics")
        return self


class CoreProcessedFeatureRow(ContractModel):
    instrument_id: Identifier
    feature_id: Identifier
    feature_definition_version: Version
    availability_state: FeatureAvailabilityState
    missing_reason_code: Identifier | None = None
    value_raw: float | None = None
    value_winsorized: float | None = None
    value_standardized_observed: float | None = None
    model_value: float | None = None
    imputation_source: CoreImputationSource
    is_missing: bool
    is_not_applicable: bool
    neutralized_diagnostic: float | None = None

    @model_validator(mode="after")
    def validate_state(self) -> CoreProcessedFeatureRow:
        if any(
            item is not None and not math.isfinite(item)
            for item in (
                self.value_raw,
                self.value_winsorized,
                self.value_standardized_observed,
                self.model_value,
                self.neutralized_diagnostic,
            )
        ):
            raise ValueError("processed feature values must be finite")
        observed = self.availability_state == FeatureAvailabilityState.OBSERVED
        missing = self.availability_state == FeatureAvailabilityState.MISSING
        not_applicable = self.availability_state == FeatureAvailabilityState.NOT_APPLICABLE
        if self.is_missing != missing or self.is_not_applicable != not_applicable:
            raise ValueError("processed indicators must preserve raw tri-state")
        if observed:
            if (
                self.value_raw is None
                or self.value_winsorized is None
                or self.value_standardized_observed is None
                or self.model_value != self.value_standardized_observed
                or self.imputation_source != CoreImputationSource.NONE
                or self.missing_reason_code is not None
            ):
                raise ValueError("observed processed row is incomplete")
        elif (
            self.value_raw is not None
            or self.value_winsorized is not None
            or self.value_standardized_observed is not None
            or self.missing_reason_code is None
        ):
            raise ValueError("non-observed row cannot masquerade as observed")
        if not_applicable and self.imputation_source == CoreImputationSource.SW_L1_MEDIAN:
            raise ValueError("not_applicable cannot use an industry median")
        return self


class CoreProcessedFeatureEnvelope(ContractModel):
    envelope_id: Identifier
    content_hash: ContentHash
    decision_date: date
    core_input_snapshot_id: Identifier
    core_input_content_hash: ContentHash
    raw_feature_snapshot_id: Identifier
    raw_feature_content_hash: ContentHash
    raw_manifest_id: Identifier
    raw_manifest_content_hash: ContentHash
    package_id: Identifier
    definition_registry_hash: ContentHash
    computation_manifest_hash: ContentHash
    universe_content_hash: ContentHash
    control_panel_id: Identifier
    control_panel_content_hash: ContentHash
    processing_spec: CoreProcessingSpec
    processing_spec_hash: ContentHash
    feature_order: tuple[Identifier, ...] = Field(min_length=1)
    instrument_order: tuple[Identifier, ...] = Field(min_length=1)
    rows: tuple[CoreProcessedFeatureRow, ...] = Field(min_length=1)
    cross_sections: tuple[CoreCrossSectionEvidence, ...] = Field(min_length=1)
    blocked_feature_ids: tuple[Identifier, ...] = ()

    @model_validator(mode="after")
    def validate_identity(self) -> CoreProcessedFeatureEnvelope:
        CoreProcessingSpec.model_validate(self.processing_spec.model_dump())
        if len(set(self.feature_order)) != len(self.feature_order) or len(
            set(self.instrument_order)
        ) != len(self.instrument_order):
            raise ValueError("processed feature and instrument orders must be unique")
        expected_keys = tuple(
            (instrument, feature)
            for instrument in self.instrument_order
            for feature in self.feature_order
        )
        actual_keys = tuple((item.instrument_id, item.feature_id) for item in self.rows)
        if actual_keys != expected_keys:
            raise ValueError("processed rows must follow instrument and feature order")
        if tuple(item.feature_id for item in self.cross_sections) != self.feature_order:
            raise ValueError("cross-section evidence must follow feature order")
        expected_blocked = tuple(
            item.feature_id
            for item in self.cross_sections
            if item.status == CoreCrossSectionStatus.NO_OBSERVED
        )
        if self.blocked_feature_ids != expected_blocked:
            raise ValueError("blocked feature list must match cross-section evidence")
        if self.processing_spec_hash != research_hash(self.processing_spec):
            raise ValueError("processing spec hash mismatch")
        expected_hash = research_hash(_processed_payload(self))
        expected_id = f"core-processed:{expected_hash.removeprefix('sha256:')}"
        if self.content_hash != expected_hash or self.envelope_id != expected_id:
            raise ValueError("processed envelope canonical identity mismatch")
        return self


def _processed_payload(envelope: CoreProcessedFeatureEnvelope) -> dict[str, object]:
    return {
        "schema": "core-processed-feature-envelope-v1",
        **{
            key: value
            for key, value in envelope.model_dump().items()
            if key not in {"envelope_id", "content_hash"}
        },
    }


__all__ = [
    "CoreCrossSectionEvidence",
    "CoreCrossSectionStatus",
    "CoreNeutralizationStatus",
    "CoreProcessedFeatureEnvelope",
    "CoreProcessedFeatureRow",
    "CoreProcessingSpec",
]
