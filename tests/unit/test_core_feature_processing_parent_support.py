"""Validated processed-envelope and panel parents for Stage S contract tests."""

from __future__ import annotations

from datetime import date, timedelta

from astramind_mini.strategy_research.application.identity import research_hash
from astramind_mini.strategy_research.core.feature_processing import (
    CoreCrossSectionEvidence,
    CoreCrossSectionStatus,
    CoreNeutralizationStatus,
    CoreProcessedFeatureEnvelope,
    CoreProcessedFeaturePanelEntry,
    CoreProcessedFeaturePanelManifest,
    CoreProcessedFeatureRow,
    CoreProcessingSpec,
)
from astramind_mini.strategy_research.core.feature_values import (
    CoreImputationSource,
    FeatureAvailabilityState,
)

HASH_A = "sha256:" + "a" * 64
HASH_B = "sha256:" + "b" * 64
START = date(2025, 1, 2)


def frozen_envelopes(
    *,
    package_id: str,
    feature_ids: tuple[str, ...],
    instruments: tuple[str, ...],
    days: int = 180,
    universe_hashes: tuple[str, ...] | None = None,
) -> tuple[CoreProcessedFeatureEnvelope, ...]:
    return tuple(
        _envelope(
            package_id=package_id,
            feature_ids=feature_ids,
            instruments=instruments,
            index=index,
            universe_hash=(
                universe_hashes[index]
                if universe_hashes is not None
                else research_hash({"u0": index})
            ),
        )
        for index in range(days)
    )


def _envelope(
    *,
    package_id: str,
    feature_ids: tuple[str, ...],
    instruments: tuple[str, ...],
    index: int,
    universe_hash: str,
) -> CoreProcessedFeatureEnvelope:
    rows = tuple(
        _processed_row(instrument, feature, position + feature_index)
        for position, instrument in enumerate(instruments)
        for feature_index, feature in enumerate(feature_ids)
    )
    cross_sections = tuple(_cross_section(feature, len(instruments)) for feature in feature_ids)
    spec = CoreProcessingSpec()
    day = START + timedelta(days=index)
    payload = {
        "schema": "core-processed-feature-envelope-v1",
        "decision_date": day,
        "core_input_snapshot_id": f"input-{package_id}-{index}",
        "core_input_content_hash": research_hash({"input": (package_id, index)}),
        "raw_feature_snapshot_id": f"raw-{package_id}-{index}",
        "raw_feature_content_hash": research_hash({"raw": (package_id, index)}),
        "raw_manifest_id": f"raw-manifest-{package_id}",
        "raw_manifest_content_hash": research_hash({"raw-manifest": package_id}),
        "package_id": package_id,
        "definition_registry_hash": HASH_A,
        "computation_manifest_hash": HASH_B,
        "universe_content_hash": universe_hash,
        "control_panel_id": f"controls-{package_id}-{index}",
        "control_panel_content_hash": research_hash({"controls": (package_id, index)}),
        "processing_spec": spec,
        "processing_spec_hash": research_hash(spec),
        "feature_order": feature_ids,
        "instrument_order": instruments,
        "rows": rows,
        "cross_sections": cross_sections,
        "blocked_feature_ids": (),
    }
    content_hash = research_hash(payload)
    return CoreProcessedFeatureEnvelope.model_validate(
        {
            "envelope_id": f"core-processed:{content_hash.removeprefix('sha256:')}",
            "content_hash": content_hash,
            **{key: value for key, value in payload.items() if key != "schema"},
        }
    )


def _cross_section(feature: str, instrument_count: int) -> CoreCrossSectionEvidence:
    return CoreCrossSectionEvidence(
        feature_id=feature,
        feature_definition_version="1.0.0",
        observed_count=instrument_count,
        missing_count=0,
        not_applicable_count=0,
        applicable_count=instrument_count,
        coverage=1.0,
        median_raw=float(instrument_count // 2),
        mad_scale=1.0,
        winsor_lower=-5.0,
        winsor_upper=5.0,
        status=CoreCrossSectionStatus.READY,
        neutralization_status=CoreNeutralizationStatus.INSUFFICIENT_SAMPLE,
        neutralization_sample_count=instrument_count,
        neutralization_parameter_count=2,
    )


def _processed_row(
    instrument: str,
    feature_id: str,
    position: int,
) -> CoreProcessedFeatureRow:
    value = float(position)
    return CoreProcessedFeatureRow(
        instrument_id=instrument,
        feature_id=feature_id,
        feature_definition_version="1.0.0",
        availability_state=FeatureAvailabilityState.OBSERVED,
        value_raw=value,
        value_winsorized=value,
        value_standardized_observed=value,
        model_value=value,
        imputation_source=CoreImputationSource.NONE,
        is_missing=False,
        is_not_applicable=False,
    )


def frozen_panel(
    envelopes: tuple[CoreProcessedFeatureEnvelope, ...],
) -> CoreProcessedFeaturePanelManifest:
    entries = tuple(
        CoreProcessedFeaturePanelEntry(
            decision_date=item.decision_date,
            core_input_snapshot_id=item.core_input_snapshot_id,
            core_input_content_hash=item.core_input_content_hash,
            raw_envelope_id=item.raw_feature_snapshot_id,
            raw_envelope_content_hash=item.raw_feature_content_hash,
            processed_envelope_id=item.envelope_id,
            processed_envelope_content_hash=item.content_hash,
            universe_content_hash=item.universe_content_hash,
            control_panel_id=item.control_panel_id,
            control_panel_content_hash=item.control_panel_content_hash,
        )
        for item in envelopes
    )
    payload = {
        "schema": "core-processed-feature-panel-v1",
        "package_id": envelopes[0].package_id,
        "feature_order": envelopes[0].feature_order,
        "entries": entries,
    }
    content_hash = research_hash(payload)
    return CoreProcessedFeaturePanelManifest(
        panel_manifest_id=f"core-processed-panel:{content_hash.removeprefix('sha256:')}",
        content_hash=content_hash,
        package_id=envelopes[0].package_id,
        feature_order=envelopes[0].feature_order,
        entries=entries,
    )


__all__ = ["frozen_envelopes", "frozen_panel"]
