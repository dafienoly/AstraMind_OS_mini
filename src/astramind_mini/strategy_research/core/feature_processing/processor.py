"""Protected daily processing entry point shared by all three factor packages."""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from typing import cast

from ...application.identity import research_hash
from ..contracts import CoreInputSnapshot, CoreUniverseDecision
from ..feature_output import CoreRawFeatureEnvelope
from ..feature_values import (
    CoreFeatureValue,
    CoreImputationSource,
    FeatureAvailabilityState,
)
from ..identity import validate_core_input_snapshot
from ..universe import core_universe_content_hash
from .control import CoreProcessingControlPanel, CoreProcessingControlRow
from .imputation import state_aware_imputation_values
from .models import (
    CoreCrossSectionEvidence,
    CoreCrossSectionStatus,
    CoreNeutralizationStatus,
    CoreProcessedFeatureEnvelope,
    CoreProcessedFeatureRow,
    CoreProcessingSpec,
)
from .neutralization import neutralization_residuals
from .transforms import robust_cross_section


def process_core_raw_feature_envelope(
    *,
    core_input: CoreInputSnapshot,
    universe_rows: Sequence[CoreUniverseDecision],
    raw_envelope: CoreRawFeatureEnvelope,
    control_panel: CoreProcessingControlPanel,
    spec: CoreProcessingSpec | None = None,
) -> CoreProcessedFeatureEnvelope:
    """Process one complete daily U0 cross-section without deleting rows."""
    rules = CoreProcessingSpec.model_validate((spec or CoreProcessingSpec()).model_dump())
    audit_rows = tuple(sorted(universe_rows, key=lambda item: item.instrument_id))
    members = tuple(item for item in audit_rows if item.research_member)
    _validate_bindings(
        core_input=core_input,
        audit_rows=audit_rows,
        members=members,
        raw_envelope=raw_envelope,
        control_panel=control_panel,
    )
    feature_order = raw_envelope.feature_order
    instruments = tuple(item.instrument_id for item in members)
    raw_by_key = {
        (item.instrument_id, item.feature_definition_id): item for item in raw_envelope.rows
    }
    controls = {item.instrument_id: item for item in control_panel.rows}
    rows_by_key: dict[tuple[str, str], CoreProcessedFeatureRow] = {}
    evidence: list[CoreCrossSectionEvidence] = []
    for feature_id in feature_order:
        feature_raw = tuple(raw_by_key[(instrument, feature_id)] for instrument in instruments)
        processed, cross_section = _process_feature(
            feature_id=feature_id,
            raw_rows=feature_raw,
            controls=controls,
            spec=rules,
        )
        rows_by_key.update({(item.instrument_id, item.feature_id): item for item in processed})
        evidence.append(cross_section)
    rows = tuple(
        rows_by_key[(instrument, feature)]
        for instrument in instruments
        for feature in feature_order
    )
    cross_sections = tuple(evidence)
    blocked = tuple(
        item.feature_id
        for item in cross_sections
        if item.status == CoreCrossSectionStatus.NO_OBSERVED
    )
    processing_spec_hash = research_hash(rules)
    payload = {
        "schema": "core-processed-feature-envelope-v1",
        "decision_date": core_input.decision_date,
        "core_input_snapshot_id": core_input.core_input_snapshot_id,
        "core_input_content_hash": core_input.content_hash,
        "raw_feature_snapshot_id": raw_envelope.feature_snapshot.feature_snapshot_id,
        "raw_feature_content_hash": raw_envelope.feature_snapshot.content_hash,
        "raw_manifest_id": raw_envelope.manifest.manifest_id,
        "raw_manifest_content_hash": raw_envelope.manifest.content_hash,
        "package_id": raw_envelope.package_spec.package_id,
        "definition_registry_hash": raw_envelope.manifest.definition_registry_hash,
        "computation_manifest_hash": raw_envelope.manifest.computation_manifest_hash,
        "universe_content_hash": core_input.universe_content_hash,
        "control_panel_id": control_panel.panel_id,
        "control_panel_content_hash": control_panel.content_hash,
        "processing_spec": rules,
        "processing_spec_hash": processing_spec_hash,
        "feature_order": feature_order,
        "instrument_order": instruments,
        "rows": rows,
        "cross_sections": cross_sections,
        "blocked_feature_ids": blocked,
    }
    content_hash = research_hash(payload)
    return CoreProcessedFeatureEnvelope.model_validate(
        {
            "envelope_id": f"core-processed:{content_hash.removeprefix('sha256:')}",
            "content_hash": content_hash,
            **{key: value for key, value in payload.items() if key != "schema"},
        }
    )


def _validate_bindings(
    *,
    core_input: CoreInputSnapshot,
    audit_rows: tuple[CoreUniverseDecision, ...],
    members: tuple[CoreUniverseDecision, ...],
    raw_envelope: CoreRawFeatureEnvelope,
    control_panel: CoreProcessingControlPanel,
) -> None:
    validate_core_input_snapshot(core_input)
    if core_universe_content_hash(audit_rows) != core_input.universe_content_hash:
        raise ValueError("processing U0 decisions do not match CoreInputSnapshot")
    if any(
        item.decision_date != core_input.decision_date or item.input_cutoff != core_input.cutoff_at
        for item in audit_rows
    ):
        raise ValueError("processing U0 decisions cross the daily input identity")
    if (
        raw_envelope.core_input_snapshot_id != core_input.core_input_snapshot_id
        or raw_envelope.manifest.core_input_content_hash != core_input.content_hash
        or raw_envelope.feature_snapshot.data_snapshot_id != core_input.data_snapshot.snapshot_id
    ):
        raise ValueError("raw envelope does not bind the exact CoreInputSnapshot")
    member_ids = tuple(item.instrument_id for item in members)
    raw_ids = tuple(sorted({item.instrument_id for item in raw_envelope.rows}))
    if raw_ids != member_ids:
        raise ValueError("raw envelope must exactly cover daily research-member U0")
    if (
        control_panel.decision_date != core_input.decision_date
        or control_panel.input_cutoff != core_input.cutoff_at
        or control_panel.universe_content_hash != core_input.universe_content_hash
        or control_panel.universe_rows != audit_rows
        or control_panel.instrument_ids != member_ids
    ):
        raise ValueError("control panel does not bind the exact daily U0 and cutoff")


def _process_feature(
    *,
    feature_id: str,
    raw_rows: Sequence[CoreFeatureValue],
    controls: dict[str, CoreProcessingControlRow],
    spec: CoreProcessingSpec,
) -> tuple[tuple[CoreProcessedFeatureRow, ...], CoreCrossSectionEvidence]:
    typed_rows = tuple(raw_rows)
    observed_rows = tuple(
        item for item in typed_rows if item.availability_state == FeatureAvailabilityState.OBSERVED
    )
    raw_values = tuple(float(cast(float, item.value_raw)) for item in observed_rows)
    (
        status,
        center,
        scale,
        lower,
        upper,
        winsorized,
        standardized,
    ) = robust_cross_section(raw_values, spec=spec)
    observed_stats = {
        item.instrument_id: (winsor, z)
        for item, winsor, z in zip(
            observed_rows,
            winsorized,
            standardized,
            strict=True,
        )
    }
    neutral_status, sample_count, parameter_count, residuals = neutralization_residuals(
        tuple((item.instrument_id, z) for item, z in zip(observed_rows, standardized, strict=True)),
        controls,
        spec=spec,
    )
    if status == CoreCrossSectionStatus.NO_OBSERVED:
        neutral_status = CoreNeutralizationStatus.INSUFFICIENT_SAMPLE
    fill_values = state_aware_imputation_values(
        typed_rows,
        standardized_by_instrument={
            item.instrument_id: z for item, z in zip(observed_rows, standardized, strict=True)
        },
        controls=controls,
        spec=spec,
    )
    rows = tuple(
        _materialize_processed_row(
            item,
            observed_stats=observed_stats,
            fill_values=fill_values,
            residuals=residuals,
        )
        for item in typed_rows
    )
    evidence = _cross_section_evidence(
        feature_id=feature_id,
        rows=typed_rows,
        status=status,
        robust_statistics=(center, scale, lower, upper),
        neutralization_status=neutral_status,
        neutralization_sample_count=sample_count,
        neutralization_parameter_count=parameter_count,
    )
    return rows, evidence


def _cross_section_evidence(
    *,
    feature_id: str,
    rows: tuple[CoreFeatureValue, ...],
    status: CoreCrossSectionStatus,
    robust_statistics: tuple[
        float | None,
        float | None,
        float | None,
        float | None,
    ],
    neutralization_status: CoreNeutralizationStatus,
    neutralization_sample_count: int,
    neutralization_parameter_count: int,
) -> CoreCrossSectionEvidence:
    counts = Counter(item.availability_state for item in rows)
    observed = counts[FeatureAvailabilityState.OBSERVED]
    missing = counts[FeatureAvailabilityState.MISSING]
    applicable = observed + missing
    center, scale, lower, upper = robust_statistics
    return CoreCrossSectionEvidence(
        feature_id=feature_id,
        feature_definition_version=rows[0].feature_definition_version,
        observed_count=observed,
        missing_count=missing,
        not_applicable_count=counts[FeatureAvailabilityState.NOT_APPLICABLE],
        applicable_count=applicable,
        coverage=observed / applicable if applicable else None,
        median_raw=center,
        mad_scale=scale,
        winsor_lower=lower,
        winsor_upper=upper,
        status=status,
        neutralization_status=neutralization_status,
        neutralization_sample_count=neutralization_sample_count,
        neutralization_parameter_count=neutralization_parameter_count,
    )


def _materialize_processed_row(
    raw: CoreFeatureValue,
    *,
    observed_stats: dict[str, tuple[float, float]],
    fill_values: dict[str, tuple[float, CoreImputationSource]],
    residuals: dict[str, float],
) -> CoreProcessedFeatureRow:
    instrument = raw.instrument_id
    state = raw.availability_state
    winsorized_value: float | None
    standardized_value: float | None
    if state == FeatureAvailabilityState.OBSERVED:
        winsorized_value, standardized_value = observed_stats[instrument]
        model_value = standardized_value
        source = CoreImputationSource.NONE
    elif instrument in fill_values:
        model_value, source = fill_values[instrument]
        winsorized_value = standardized_value = None
    else:
        model_value = None
        source = CoreImputationSource.NONE
        winsorized_value = standardized_value = None
    return CoreProcessedFeatureRow(
        instrument_id=instrument,
        feature_id=raw.feature_definition_id,
        feature_definition_version=raw.feature_definition_version,
        availability_state=state,
        missing_reason_code=raw.missing_reason_code,
        value_raw=raw.value_raw,
        value_winsorized=winsorized_value,
        value_standardized_observed=standardized_value,
        model_value=model_value,
        imputation_source=source,
        is_missing=state == FeatureAvailabilityState.MISSING,
        is_not_applicable=state == FeatureAvailabilityState.NOT_APPLICABLE,
        neutralized_diagnostic=residuals.get(instrument),
    )


__all__ = ["process_core_raw_feature_envelope"]
