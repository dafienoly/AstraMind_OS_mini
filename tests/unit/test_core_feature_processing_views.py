from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date

import pytest

from astramind_mini.strategy_research.application.identity import research_hash
from astramind_mini.strategy_research.core.feature_processing import (
    CoreCrossSectionEvidence,
    CoreCrossSectionStatus,
    CoreFeatureViewKind,
    CoreFeatureViewStatus,
    CoreNeutralizationStatus,
    CoreProcessedFeatureEnvelope,
    CoreProcessedFeaturePanelEntry,
    CoreProcessedFeaturePanelManifest,
    CoreProcessedFeatureRow,
    CoreProcessingSpec,
    build_core_feature_view_manifest,
    project_core_feature_matrix,
)
from astramind_mini.strategy_research.core.feature_values import (
    CoreImputationSource,
    FeatureAvailabilityState,
)
from astramind_mini.strategy_research.core.labels import CoreLabelHorizon

HASH_A = "sha256:" + "a" * 64
HASH_B = "sha256:" + "b" * 64
DAY = date(2025, 1, 2)


@dataclass(frozen=True)
class _Coverage:
    passed: bool


@dataclass(frozen=True)
class _Evidence:
    feature_key: str
    coverage: _Coverage


@dataclass(frozen=True)
class _Selection:
    package_id: str
    horizon: CoreLabelHorizon
    panel_manifest_id: str
    panel_content_hash: str
    manifest_id: str
    content_hash: str
    feature_evidence: tuple[_Evidence, ...]
    selected_feature_keys: tuple[str, ...]
    selected_feature_ids: tuple[str, ...]


def _row(instrument: str, feature_id: str, value: float) -> CoreProcessedFeatureRow:
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


def _envelope() -> CoreProcessedFeatureEnvelope:
    features = ("F1", "F2")
    instruments = ("A", "B")
    rows = tuple(
        _row(instrument, feature, float(instrument == "B") + index)
        for instrument in instruments
        for index, feature in enumerate(features)
    )
    cross_sections = tuple(
        CoreCrossSectionEvidence(
            feature_id=feature,
            feature_definition_version="1.0.0",
            observed_count=2,
            missing_count=0,
            not_applicable_count=0,
            applicable_count=2,
            coverage=1.0,
            median_raw=0.5,
            mad_scale=1.0,
            winsor_lower=-4.5,
            winsor_upper=5.5,
            status=CoreCrossSectionStatus.READY,
            neutralization_status=CoreNeutralizationStatus.INSUFFICIENT_SAMPLE,
            neutralization_sample_count=2,
            neutralization_parameter_count=2,
        )
        for feature in features
    )
    spec = CoreProcessingSpec()
    payload = {
        "schema": "core-processed-feature-envelope-v1",
        "decision_date": DAY,
        "core_input_snapshot_id": "input",
        "core_input_content_hash": HASH_A,
        "raw_feature_snapshot_id": "raw",
        "raw_feature_content_hash": HASH_A,
        "raw_manifest_id": "raw-manifest",
        "raw_manifest_content_hash": HASH_A,
        "package_id": "fixture-package",
        "definition_registry_hash": HASH_A,
        "computation_manifest_hash": HASH_B,
        "universe_content_hash": HASH_A,
        "control_panel_id": "controls",
        "control_panel_content_hash": HASH_B,
        "processing_spec": spec,
        "processing_spec_hash": research_hash(spec),
        "feature_order": features,
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


def _panel(envelope: CoreProcessedFeatureEnvelope) -> CoreProcessedFeaturePanelManifest:
    entry = CoreProcessedFeaturePanelEntry(
        decision_date=DAY,
        core_input_snapshot_id="input",
        core_input_content_hash=HASH_A,
        raw_envelope_id="raw",
        raw_envelope_content_hash=HASH_A,
        processed_envelope_id=envelope.envelope_id,
        processed_envelope_content_hash=envelope.content_hash,
        universe_content_hash=HASH_A,
        control_panel_id="controls",
        control_panel_content_hash=HASH_B,
    )
    payload = {
        "schema": "core-processed-feature-panel-v1",
        "package_id": envelope.package_id,
        "feature_order": envelope.feature_order,
        "entries": (entry,),
    }
    content_hash = research_hash(payload)
    return CoreProcessedFeaturePanelManifest(
        panel_manifest_id=f"core-processed-panel:{content_hash.removeprefix('sha256:')}",
        content_hash=content_hash,
        package_id=envelope.package_id,
        feature_order=envelope.feature_order,
        entries=(entry,),
    )


def _selection(
    panel: CoreProcessedFeaturePanelManifest,
    *,
    passed: tuple[bool, bool] = (True, True),
    selected: tuple[str, ...] = ("F1",),
) -> _Selection:
    return _Selection(
        package_id=panel.package_id,
        horizon=CoreLabelHorizon.H20,
        panel_manifest_id=panel.panel_manifest_id,
        panel_content_hash=panel.content_hash,
        manifest_id="selection",
        content_hash=HASH_A,
        feature_evidence=tuple(
            _Evidence(f"{feature}@1.0.0", _Coverage(ok))
            for feature, ok in zip(panel.feature_order, passed, strict=True)
        ),
        selected_feature_keys=tuple(f"{feature}@1.0.0" for feature in selected),
        selected_feature_ids=selected,
    )


def test_full_and_selected_views_project_exact_finite_fixed_columns() -> None:
    envelope = _envelope()
    panel = _panel(envelope)
    selection = _selection(panel)
    full = build_core_feature_view_manifest(
        panel_manifest=panel,
        processed_envelopes=(envelope,),
        selection_manifest=selection,
        view_kind=CoreFeatureViewKind.FULL,
    )
    selected = build_core_feature_view_manifest(
        panel_manifest=panel,
        processed_envelopes=(envelope,),
        selection_manifest=selection,
        view_kind=CoreFeatureViewKind.SELECTED,
    )
    assert full.feature_ids == ("F1", "F2")
    assert selected.feature_ids == ("F1",)
    assert full.view_id != selected.view_id
    projection = project_core_feature_matrix(envelope=envelope, view=selected)
    assert projection.row_order == ("A", "B")
    assert projection.column_order == (
        "F1__value",
        "F1__is_missing",
        "F1__is_not_applicable",
    )
    assert projection.values == ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0))


def test_coverage_and_empty_selection_publish_blocked_non_projectable_views() -> None:
    envelope = _envelope()
    panel = _panel(envelope)
    blocked_full = build_core_feature_view_manifest(
        panel_manifest=panel,
        processed_envelopes=(envelope,),
        selection_manifest=_selection(panel, passed=(False, True)),
        view_kind=CoreFeatureViewKind.FULL,
    )
    empty_selected = build_core_feature_view_manifest(
        panel_manifest=panel,
        processed_envelopes=(envelope,),
        selection_manifest=_selection(panel, selected=()),
        view_kind=CoreFeatureViewKind.SELECTED,
    )
    assert blocked_full.status == CoreFeatureViewStatus.BLOCKED
    assert empty_selected.status == CoreFeatureViewStatus.BLOCKED
    assert empty_selected.blocker_codes == ("selection_empty",)
    assert empty_selected.model_input_dimension == 0
    with pytest.raises(ValueError, match="blocked"):
        project_core_feature_matrix(envelope=envelope, view=empty_selected)


def test_rehashed_processed_row_still_rejects_non_finite_observed_value() -> None:
    data = _row("A", "F", 1.0).model_dump()
    data["model_value"] = math.inf
    with pytest.raises(ValueError, match="finite"):
        CoreProcessedFeatureRow.model_validate(data)
