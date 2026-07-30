"""Two-stage builder for immutable raw core formula outputs."""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from datetime import datetime

from astramind_mini.contracts import FeatureSnapshot

from .contracts import CoreFeaturePackageSpec, CoreInputSnapshot
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
from .feature_output import (
    CoreFeatureCoverage,
    CoreFeatureRowIdentity,
    CoreRawFeatureBatchDraft,
    CoreRawFeatureEnvelope,
    CoreRawFeatureManifest,
    state_counts,
)
from .feature_values import (
    CoreFeatureValue,
    CoreImputationSource,
    CoreRawFeatureRowDraft,
    FeatureAvailabilityState,
)
from .packages import CORE_FEATURE_PACKAGES


def prepare_core_raw_feature_batch(
    *,
    core_input: CoreInputSnapshot,
    package_spec: CoreFeaturePackageSpec,
    feature_order: Sequence[str],
    rows: Sequence[CoreRawFeatureRowDraft],
) -> CoreRawFeatureBatchDraft:
    """Canonicalize snapshot-free row drafts and derive their content identity."""
    if package_spec not in CORE_FEATURE_PACKAGES:
        raise ValueError("raw core features require a canonical package spec")
    ordered_features = tuple(feature_order)
    if len(ordered_features) != package_spec.canonical_dimension:
        raise ValueError("feature_order width must equal the canonical package dimension")
    if len(set(ordered_features)) != len(ordered_features):
        raise ValueError("feature_order cannot contain duplicate definitions")
    if not rows:
        raise ValueError("raw core feature output cannot be empty")

    canonical_rows = _canonical_rows(
        rows,
        feature_order=ordered_features,
        decision_time=core_input.cutoff_at,
    )
    row_content_hashes = canonical_row_content_hashes(canonical_rows)
    rows_content_hash = canonical_rows_content_hash(row_content_hashes)
    package_spec_hash = canonical_package_spec_hash(package_spec)
    registry_hash = canonical_definition_registry_hash(ordered_features, canonical_rows)
    content_hash = canonical_raw_snapshot_content_hash(
        core_input_snapshot_id=core_input.core_input_snapshot_id,
        core_input_content_hash=core_input.content_hash,
        data_snapshot_id=core_input.data_snapshot.snapshot_id,
        decision_time=core_input.cutoff_at,
        package_spec_hash=package_spec_hash,
        definition_registry_hash=registry_hash,
        feature_order=ordered_features,
        rows_content_hash=rows_content_hash,
    )
    return CoreRawFeatureBatchDraft(
        feature_snapshot_id=canonical_feature_snapshot_id(content_hash),
        content_hash=content_hash,
        rows_content_hash=rows_content_hash,
        row_content_hashes=row_content_hashes,
        core_input_snapshot_id=core_input.core_input_snapshot_id,
        core_input_content_hash=core_input.content_hash,
        data_snapshot_id=core_input.data_snapshot.snapshot_id,
        decision_time=core_input.cutoff_at,
        package_spec=package_spec,
        package_spec_hash=package_spec_hash,
        definition_registry_hash=registry_hash,
        feature_order=ordered_features,
        rows=canonical_rows,
    )


def finalize_core_raw_feature_envelope(
    draft: CoreRawFeatureBatchDraft,
) -> CoreRawFeatureEnvelope:
    """Inject one FeatureSnapshot identity after the snapshot-free hash is stable."""
    feature_snapshot = FeatureSnapshot(
        feature_snapshot_id=draft.feature_snapshot_id,
        data_snapshot_id=draft.data_snapshot_id,
        as_of=draft.decision_time,
        definition_version=f"{draft.package_spec.package_id}-raw-v1",
        content_hash=draft.content_hash,
    )
    rows = tuple(_materialize_row(item, draft.feature_snapshot_id) for item in draft.rows)
    manifest = _build_manifest(draft)
    return CoreRawFeatureEnvelope(
        feature_snapshot=feature_snapshot,
        core_input_snapshot_id=draft.core_input_snapshot_id,
        package_spec=draft.package_spec,
        feature_order=draft.feature_order,
        rows=rows,
        manifest=manifest,
    )


def build_core_raw_feature_envelope(
    *,
    core_input: CoreInputSnapshot,
    package_spec: CoreFeaturePackageSpec,
    feature_order: Sequence[str],
    rows: Sequence[CoreRawFeatureRowDraft],
) -> CoreRawFeatureEnvelope:
    draft = prepare_core_raw_feature_batch(
        core_input=core_input,
        package_spec=package_spec,
        feature_order=feature_order,
        rows=rows,
    )
    return finalize_core_raw_feature_envelope(draft)


def _canonical_rows(
    rows: Sequence[CoreRawFeatureRowDraft],
    *,
    feature_order: tuple[str, ...],
    decision_time: datetime,
) -> tuple[CoreRawFeatureRowDraft, ...]:
    if any(item.decision_time != decision_time for item in rows):
        raise ValueError("all raw rows must use the CoreInputSnapshot cutoff")
    feature_positions = {feature_id: index for index, feature_id in enumerate(feature_order)}
    if any(item.feature_definition_id not in feature_positions for item in rows):
        raise ValueError("raw row contains a feature outside canonical feature_order")

    keys = [(item.instrument_id, item.feature_definition_id) for item in rows]
    if len(keys) != len(set(keys)):
        raise ValueError("raw rows cannot duplicate an instrument-feature identity")
    instruments = sorted({item.instrument_id for item in rows})
    expected_count = len(instruments) * len(feature_order)
    if len(rows) != expected_count:
        raise ValueError("every instrument must provide the complete canonical package width")
    versions: dict[str, set[str]] = {feature_id: set() for feature_id in feature_order}
    for item in rows:
        versions[item.feature_definition_id].add(item.feature_definition_version)
    if any(len(items) != 1 for items in versions.values()):
        raise ValueError("each feature definition must use one version across the batch")
    return tuple(
        sorted(
            rows,
            key=lambda item: (
                item.instrument_id,
                feature_positions[item.feature_definition_id],
            ),
        )
    )


def _materialize_row(
    draft: CoreRawFeatureRowDraft,
    feature_snapshot_id: str,
) -> CoreFeatureValue:
    return CoreFeatureValue(
        feature_snapshot_id=feature_snapshot_id,
        instrument_id=draft.instrument_id,
        decision_time=draft.decision_time,
        feature_definition_id=draft.feature_definition_id,
        feature_definition_version=draft.feature_definition_version,
        value_raw=draft.value_raw,
        availability_state=draft.availability_state,
        missing_reason_code=draft.missing_reason_code,
        value_winsorized=None,
        value_standardized=None,
        imputation_source=CoreImputationSource.NONE,
        missing_indicator=draft.availability_state == FeatureAvailabilityState.MISSING,
        not_applicable_indicator=(
            draft.availability_state == FeatureAvailabilityState.NOT_APPLICABLE
        ),
        neutralized_diagnostic=None,
        data_semantics_version="core-data-semantics-v1",
    )


def _build_manifest(draft: CoreRawFeatureBatchDraft) -> CoreRawFeatureManifest:
    observed, missing, not_applicable = state_counts(draft.rows)
    row_order = tuple(
        CoreFeatureRowIdentity(
            ordinal=index,
            instrument_id=item.instrument_id,
            decision_time=item.decision_time,
            feature_definition_id=item.feature_definition_id,
            feature_definition_version=item.feature_definition_version,
        )
        for index, item in enumerate(draft.rows)
    )
    coverage = tuple(
        _feature_coverage(feature_id, draft.rows) for feature_id in draft.feature_order
    )
    instruments = {item.instrument_id for item in draft.rows}
    content_hash = canonical_manifest_content_hash(
        rows_content_hash=draft.rows_content_hash,
        row_content_hashes=draft.row_content_hashes,
        feature_snapshot_id=draft.feature_snapshot_id,
        core_input_snapshot_id=draft.core_input_snapshot_id,
        core_input_content_hash=draft.core_input_content_hash,
        package_spec_hash=draft.package_spec_hash,
        definition_registry_hash=draft.definition_registry_hash,
        package_id=draft.package_spec.package_id,
        feature_order=draft.feature_order,
        row_order=row_order,
        feature_coverage=coverage,
        row_count=len(draft.rows),
        instrument_count=len(instruments),
        observed_count=observed,
        missing_count=missing,
        not_applicable_count=not_applicable,
        observed_coverage_ratio=observed / len(draft.rows),
    )
    return CoreRawFeatureManifest(
        manifest_id=canonical_manifest_id(content_hash),
        content_hash=content_hash,
        rows_content_hash=draft.rows_content_hash,
        row_content_hashes=draft.row_content_hashes,
        feature_snapshot_id=draft.feature_snapshot_id,
        core_input_snapshot_id=draft.core_input_snapshot_id,
        core_input_content_hash=draft.core_input_content_hash,
        package_spec=draft.package_spec,
        package_spec_hash=draft.package_spec_hash,
        definition_registry_hash=draft.definition_registry_hash,
        package_id=draft.package_spec.package_id,
        feature_order=draft.feature_order,
        row_order=row_order,
        feature_coverage=coverage,
        row_count=len(draft.rows),
        instrument_count=len(instruments),
        observed_count=observed,
        missing_count=missing,
        not_applicable_count=not_applicable,
        observed_coverage_ratio=observed / len(draft.rows),
    )


def _feature_coverage(
    feature_id: str,
    rows: tuple[CoreRawFeatureRowDraft, ...],
) -> CoreFeatureCoverage:
    states = Counter(
        item.availability_state for item in rows if item.feature_definition_id == feature_id
    )
    row_count = sum(states.values())
    observed = states[FeatureAvailabilityState.OBSERVED]
    return CoreFeatureCoverage(
        feature_definition_id=feature_id,
        row_count=row_count,
        observed_count=observed,
        missing_count=states[FeatureAvailabilityState.MISSING],
        not_applicable_count=states[FeatureAvailabilityState.NOT_APPLICABLE],
        observed_coverage_ratio=observed / row_count,
    )


__all__ = [
    "build_core_raw_feature_envelope",
    "finalize_core_raw_feature_envelope",
    "prepare_core_raw_feature_batch",
]
