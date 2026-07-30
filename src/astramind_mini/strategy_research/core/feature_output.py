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
from .feature_identity import (
    canonical_definition_registry_hash,
    canonical_feature_snapshot_id,
    canonical_manifest_content_hash,
    canonical_manifest_id,
    canonical_package_spec_hash,
    canonical_raw_snapshot_content_hash,
    canonical_row_content_hashes,
    canonical_rows_content_hash,
)
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
    row_content_hashes: tuple[ContentHash, ...] = Field(min_length=1)
    core_input_snapshot_id: Identifier
    core_input_content_hash: ContentHash
    data_snapshot_id: Identifier
    decision_time: AwareDatetime
    package_spec: CoreFeaturePackageSpec
    package_spec_hash: ContentHash
    definition_registry_hash: ContentHash
    feature_order: tuple[Identifier, ...] = Field(min_length=1)
    rows: tuple[CoreRawFeatureRowDraft, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_identity(self) -> CoreRawFeatureBatchDraft:
        row_hashes = canonical_row_content_hashes(self.rows)
        rows_hash = canonical_rows_content_hash(row_hashes)
        package_hash = canonical_package_spec_hash(self.package_spec)
        registry_hash = canonical_definition_registry_hash(self.feature_order, self.rows)
        content_hash = canonical_raw_snapshot_content_hash(
            core_input_snapshot_id=self.core_input_snapshot_id,
            core_input_content_hash=self.core_input_content_hash,
            data_snapshot_id=self.data_snapshot_id,
            decision_time=self.decision_time,
            package_spec_hash=package_hash,
            definition_registry_hash=registry_hash,
            feature_order=self.feature_order,
            rows_content_hash=rows_hash,
        )
        expected = (
            row_hashes,
            rows_hash,
            package_hash,
            registry_hash,
            content_hash,
            canonical_feature_snapshot_id(content_hash),
        )
        actual = (
            self.row_content_hashes,
            self.rows_content_hash,
            self.package_spec_hash,
            self.definition_registry_hash,
            self.content_hash,
            self.feature_snapshot_id,
        )
        if actual != expected:
            raise ValueError("raw feature draft canonical identity mismatch")
        return self


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
    row_content_hashes: tuple[ContentHash, ...] = Field(min_length=1)
    feature_snapshot_id: Identifier
    core_input_snapshot_id: Identifier
    core_input_content_hash: ContentHash
    package_spec: CoreFeaturePackageSpec
    package_spec_hash: ContentHash
    definition_registry_hash: ContentHash
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
        if self.package_id != self.package_spec.package_id:
            raise ValueError("manifest package identity does not match package spec")
        if self.package_spec_hash != canonical_package_spec_hash(self.package_spec):
            raise ValueError("manifest package spec hash mismatch")
        registry_hash = canonical_definition_registry_hash(
            self.feature_order,
            self.row_order,
        )
        if self.definition_registry_hash != registry_hash:
            raise ValueError("manifest definition registry hash mismatch")
        if len(self.row_content_hashes) != self.row_count:
            raise ValueError("manifest row hashes must match row_count")
        if self.rows_content_hash != canonical_rows_content_hash(self.row_content_hashes):
            raise ValueError("manifest rows content hash mismatch")
        content_hash = _manifest_content_hash(self)
        if (
            self.content_hash != content_hash
            or self.manifest_id != canonical_manifest_id(content_hash)
        ):
            raise ValueError("raw feature manifest canonical identity mismatch")
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
        if self.manifest.package_spec != self.package_spec:
            raise ValueError("manifest package spec must match the envelope package")
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
        _validate_envelope_content_identity(self)
        if self.feature_snapshot.as_of != self.rows[0].decision_time:
            raise ValueError("FeatureSnapshot as_of must match raw row decision time")
        expected_definition = f"{self.package_spec.package_id}-raw-v1"
        if self.feature_snapshot.definition_version != expected_definition:
            raise ValueError("FeatureSnapshot definition version mismatch")
        if any(item.value_winsorized is not None for item in self.rows):
            raise ValueError("raw formula envelopes cannot contain processed values")
        if any(item.value_standardized is not None for item in self.rows):
            raise ValueError("raw formula envelopes cannot contain processed values")
        if any(item.neutralized_diagnostic is not None for item in self.rows):
            raise ValueError("raw formula envelopes cannot contain diagnostics")
        return self


def _validate_envelope_content_identity(envelope: CoreRawFeatureEnvelope) -> None:
    row_hashes = canonical_row_content_hashes(envelope.rows)
    if envelope.manifest.row_content_hashes != row_hashes:
        raise ValueError("manifest row hashes must match envelope rows")
    if envelope.manifest.rows_content_hash != canonical_rows_content_hash(row_hashes):
        raise ValueError("envelope rows content hash mismatch")
    package_hash = canonical_package_spec_hash(envelope.package_spec)
    registry_hash = canonical_definition_registry_hash(
        envelope.feature_order,
        envelope.rows,
    )
    if (
        envelope.manifest.package_spec_hash != package_hash
        or envelope.manifest.definition_registry_hash != registry_hash
    ):
        raise ValueError("envelope package or definition registry hash mismatch")
    snapshot_hash = canonical_raw_snapshot_content_hash(
        core_input_snapshot_id=envelope.core_input_snapshot_id,
        core_input_content_hash=envelope.manifest.core_input_content_hash,
        data_snapshot_id=envelope.feature_snapshot.data_snapshot_id,
        decision_time=envelope.feature_snapshot.as_of,
        package_spec_hash=package_hash,
        definition_registry_hash=registry_hash,
        feature_order=envelope.feature_order,
        rows_content_hash=envelope.manifest.rows_content_hash,
    )
    if (
        envelope.feature_snapshot.content_hash != snapshot_hash
        or envelope.feature_snapshot.feature_snapshot_id
        != canonical_feature_snapshot_id(snapshot_hash)
    ):
        raise ValueError("shared FeatureSnapshot canonical identity mismatch")


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


def _manifest_content_hash(manifest: CoreRawFeatureManifest) -> str:
    return canonical_manifest_content_hash(
        rows_content_hash=manifest.rows_content_hash,
        row_content_hashes=manifest.row_content_hashes,
        feature_snapshot_id=manifest.feature_snapshot_id,
        core_input_snapshot_id=manifest.core_input_snapshot_id,
        core_input_content_hash=manifest.core_input_content_hash,
        package_spec_hash=manifest.package_spec_hash,
        definition_registry_hash=manifest.definition_registry_hash,
        package_id=manifest.package_id,
        feature_order=manifest.feature_order,
        row_order=manifest.row_order,
        feature_coverage=manifest.feature_coverage,
        row_count=manifest.row_count,
        instrument_count=manifest.instrument_count,
        observed_count=manifest.observed_count,
        missing_count=manifest.missing_count,
        not_applicable_count=manifest.not_applicable_count,
        observed_coverage_ratio=manifest.observed_coverage_ratio,
    )


__all__ = [
    "CoreFeatureCoverage",
    "CoreFeatureRowIdentity",
    "CoreRawFeatureBatchDraft",
    "CoreRawFeatureEnvelope",
    "CoreRawFeatureManifest",
    "state_counts",
]
