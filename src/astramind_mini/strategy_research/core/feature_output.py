"""Raw formula-output envelope contracts owned by Strategy Research core."""

from __future__ import annotations

from pydantic import Field, model_validator

from astramind_mini.contracts import FeatureSnapshot
from astramind_mini.contracts.base import (
    AwareDatetime,
    ContentHash,
    ContractModel,
    Identifier,
    Version,
)

from .contracts import CoreFeaturePackageSpec
from .feature_values import (
    CoreFeatureValue,
    CoreRawFeatureRowDraft,
    FeatureAvailabilityState,
)


class CoreRawFeatureBatchDraft(ContractModel):
    """Canonical rows plus identity, still without row-level snapshot IDs."""

    feature_snapshot_id: Identifier
    content_hash: ContentHash
    rows_content_hash: ContentHash
    core_input_snapshot_id: Identifier
    data_snapshot_id: Identifier
    decision_time: AwareDatetime
    package_spec: CoreFeaturePackageSpec
    feature_order: tuple[Identifier, ...] = Field(min_length=1)
    rows: tuple[CoreRawFeatureRowDraft, ...] = Field(min_length=1)


class CoreFeatureRowIdentity(ContractModel):
    ordinal: int = Field(ge=0)
    instrument_id: Identifier
    decision_time: AwareDatetime
    feature_definition_id: Identifier
    feature_definition_version: Version


class CoreFeatureCoverage(ContractModel):
    feature_definition_id: Identifier
    row_count: int = Field(gt=0)
    observed_count: int = Field(ge=0)
    missing_count: int = Field(ge=0)
    not_applicable_count: int = Field(ge=0)
    observed_coverage_ratio: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_counts(self) -> CoreFeatureCoverage:
        total = self.observed_count + self.missing_count + self.not_applicable_count
        if total != self.row_count:
            raise ValueError("feature coverage counts must equal row_count")
        if self.observed_coverage_ratio != self.observed_count / self.row_count:
            raise ValueError("observed coverage ratio does not match counts")
        return self


class CoreRawFeatureManifest(ContractModel):
    manifest_id: Identifier
    content_hash: ContentHash
    rows_content_hash: ContentHash
    feature_snapshot_id: Identifier
    core_input_snapshot_id: Identifier
    package_id: Identifier
    feature_order: tuple[Identifier, ...] = Field(min_length=1)
    row_order: tuple[CoreFeatureRowIdentity, ...] = Field(min_length=1)
    feature_coverage: tuple[CoreFeatureCoverage, ...] = Field(min_length=1)
    row_count: int = Field(gt=0)
    instrument_count: int = Field(gt=0)
    observed_count: int = Field(ge=0)
    missing_count: int = Field(ge=0)
    not_applicable_count: int = Field(ge=0)
    observed_coverage_ratio: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_manifest(self) -> CoreRawFeatureManifest:
        if len(self.row_order) != self.row_count:
            raise ValueError("row_order length must equal row_count")
        if tuple(item.ordinal for item in self.row_order) != tuple(range(self.row_count)):
            raise ValueError("row ordinals must be contiguous and ordered")
        total = self.observed_count + self.missing_count + self.not_applicable_count
        if total != self.row_count:
            raise ValueError("manifest state counts must equal row_count")
        if self.observed_coverage_ratio != self.observed_count / self.row_count:
            raise ValueError("manifest coverage ratio does not match counts")
        return self


class CoreRawFeatureEnvelope(ContractModel):
    feature_snapshot: FeatureSnapshot
    core_input_snapshot_id: Identifier
    package_spec: CoreFeaturePackageSpec
    feature_order: tuple[Identifier, ...] = Field(min_length=1)
    rows: tuple[CoreFeatureValue, ...] = Field(min_length=1)
    manifest: CoreRawFeatureManifest

    @model_validator(mode="after")
    def validate_envelope(self) -> CoreRawFeatureEnvelope:
        snapshot_id = self.feature_snapshot.feature_snapshot_id
        if any(item.feature_snapshot_id != snapshot_id for item in self.rows):
            raise ValueError("all feature rows must bind the same FeatureSnapshot")
        if self.manifest.feature_snapshot_id != snapshot_id:
            raise ValueError("manifest must bind the envelope FeatureSnapshot")
        if self.manifest.core_input_snapshot_id != self.core_input_snapshot_id:
            raise ValueError("manifest must bind the envelope CoreInputSnapshot")
        if self.manifest.package_id != self.package_spec.package_id:
            raise ValueError("manifest package must match the envelope package")
        if self.manifest.feature_order != self.feature_order:
            raise ValueError("manifest feature order must match the envelope")
        if self.manifest.row_count != len(self.rows):
            raise ValueError("manifest row count must match the envelope rows")
        if (
            len(self.feature_order) != self.package_spec.canonical_dimension
            or len(set(self.feature_order)) != len(self.feature_order)
        ):
            raise ValueError("envelope feature order must be canonical and unique")
        row_keys = {
            (item.instrument_id, item.feature_definition_id) for item in self.rows
        }
        instruments = {item.instrument_id for item in self.rows}
        if len(row_keys) != len(self.rows):
            raise ValueError("envelope rows cannot contain duplicate identities")
        if len(self.rows) != len(instruments) * len(self.feature_order):
            raise ValueError("each envelope instrument must have the canonical width")
        if self.manifest.instrument_count != len(instruments):
            raise ValueError("manifest instrument count must match envelope rows")
        expected_order = tuple(
            (
                index,
                item.instrument_id,
                item.decision_time,
                item.feature_definition_id,
                item.feature_definition_version,
            )
            for index, item in enumerate(self.rows)
        )
        actual_order = tuple(
            (
                item.ordinal,
                item.instrument_id,
                item.decision_time,
                item.feature_definition_id,
                item.feature_definition_version,
            )
            for item in self.manifest.row_order
        )
        if actual_order != expected_order:
            raise ValueError("manifest row identities must exactly match envelope order")
        if state_counts(self.rows) != (
            self.manifest.observed_count,
            self.manifest.missing_count,
            self.manifest.not_applicable_count,
        ):
            raise ValueError("manifest state counts must match envelope rows")
        actual_coverage = tuple(
            _coverage_tuple(feature_id, self.rows) for feature_id in self.feature_order
        )
        manifest_coverage = tuple(
            (
                item.feature_definition_id,
                item.row_count,
                item.observed_count,
                item.missing_count,
                item.not_applicable_count,
            )
            for item in self.manifest.feature_coverage
        )
        if manifest_coverage != actual_coverage:
            raise ValueError("manifest feature coverage must match envelope rows")
        if any(item.value_winsorized is not None for item in self.rows):
            raise ValueError("raw formula envelopes cannot contain processed values")
        if any(item.value_standardized is not None for item in self.rows):
            raise ValueError("raw formula envelopes cannot contain processed values")
        if any(item.neutralized_diagnostic is not None for item in self.rows):
            raise ValueError("raw formula envelopes cannot contain diagnostics")
        return self


def state_counts(
    rows: tuple[CoreRawFeatureRowDraft, ...] | tuple[CoreFeatureValue, ...],
) -> tuple[int, int, int]:
    return (
        sum(item.availability_state == FeatureAvailabilityState.OBSERVED for item in rows),
        sum(item.availability_state == FeatureAvailabilityState.MISSING for item in rows),
        sum(item.availability_state == FeatureAvailabilityState.NOT_APPLICABLE for item in rows),
    )


def _coverage_tuple(
    feature_id: str,
    rows: tuple[CoreFeatureValue, ...],
) -> tuple[str, int, int, int, int]:
    feature_rows = tuple(item for item in rows if item.feature_definition_id == feature_id)
    observed, missing, not_applicable = state_counts(feature_rows)
    return feature_id, len(feature_rows), observed, missing, not_applicable


__all__ = [
    "CoreFeatureCoverage",
    "CoreFeatureRowIdentity",
    "CoreRawFeatureBatchDraft",
    "CoreRawFeatureEnvelope",
    "CoreRawFeatureManifest",
    "state_counts",
]
