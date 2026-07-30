from __future__ import annotations

import math

import pytest
from test_core_feature_selection_support import (
    frozen_envelopes,
    frozen_panel,
    frozen_selection,
)

from astramind_mini.strategy_research.application.identity import research_hash
from astramind_mini.strategy_research.core.feature_processing import (
    CoreFeatureViewKind,
    CoreFeatureViewManifest,
    CoreFeatureViewStatus,
    CoreProcessedFeatureEnvelope,
    CoreProcessedFeaturePanelManifest,
    CoreProcessedFeatureRow,
    build_core_feature_view_manifest,
    project_core_feature_matrix,
)
from astramind_mini.strategy_research.core.feature_selection import (
    CoreFeatureSelectionManifest,
)
from astramind_mini.strategy_research.core.feature_values import (
    CoreImputationSource,
    FeatureAvailabilityState,
)

PACKAGE = "fixture-package"
FEATURES = ("F1", "F2")
INSTRUMENTS = ("A", "B", "C", "D", "E")


def _parents(
    *,
    p_values: tuple[float | None, float | None] = (0.01, 0.20),
    coverage_passed: tuple[bool, bool] = (True, True),
) -> tuple[
    tuple[CoreProcessedFeatureEnvelope, ...],
    CoreProcessedFeaturePanelManifest,
    CoreFeatureSelectionManifest,
]:
    envelopes = frozen_envelopes(
        package_id=PACKAGE,
        feature_ids=FEATURES,
        instruments=INSTRUMENTS,
    )
    panel = frozen_panel(envelopes)
    selection = frozen_selection(
        panel=panel,
        envelopes=envelopes,
        p_values=p_values,
        coverage_passed=coverage_passed,
    )
    return envelopes, panel, selection


def test_full_and_selected_views_project_exact_finite_fixed_columns() -> None:
    envelopes, panel, selection = _parents()
    full = build_core_feature_view_manifest(
        panel_manifest=panel,
        processed_envelopes=envelopes,
        selection_manifest=selection,
        view_kind=CoreFeatureViewKind.FULL,
    )
    selected = build_core_feature_view_manifest(
        panel_manifest=panel,
        processed_envelopes=envelopes,
        selection_manifest=selection,
        view_kind=CoreFeatureViewKind.SELECTED,
    )
    assert full.feature_ids == FEATURES
    assert selected.feature_ids == ("F1",)
    assert full.view_id != selected.view_id
    projection = project_core_feature_matrix(
        envelope=envelopes[0],
        view=selected,
        panel_manifest=panel,
        processed_envelopes=envelopes,
        selection_manifest=selection,
    )
    assert projection.row_order == INSTRUMENTS
    assert projection.column_order == (
        "F1__value",
        "F1__is_missing",
        "F1__is_not_applicable",
    )
    assert projection.values[0] == (0.0, 0.0, 0.0)


def test_views_require_real_panel_selection_and_daily_lineage_parents() -> None:
    envelopes, panel, selection = _parents(coverage_passed=(False, True))
    blocked_full = build_core_feature_view_manifest(
        panel_manifest=panel,
        processed_envelopes=envelopes,
        selection_manifest=selection,
        view_kind=CoreFeatureViewKind.FULL,
    )
    _, _, empty_selection = _parents(p_values=(0.20, 0.20))
    empty_selected = build_core_feature_view_manifest(
        panel_manifest=panel,
        processed_envelopes=envelopes,
        selection_manifest=empty_selection,
        view_kind=CoreFeatureViewKind.SELECTED,
    )
    assert blocked_full.status == CoreFeatureViewStatus.BLOCKED
    assert empty_selected.status == CoreFeatureViewStatus.BLOCKED
    assert empty_selected.blocker_codes == ("selection_empty",)
    with pytest.raises(ValueError, match="blocked"):
        project_core_feature_matrix(
            envelope=envelopes[0],
            view=empty_selected,
            panel_manifest=panel,
            processed_envelopes=envelopes,
            selection_manifest=empty_selection,
        )

    attack = empty_selected.model_dump()
    attack["feature_ids"] = ("F2",)
    attack["feature_keys"] = ("F2@1.0.0",)
    attack["model_columns"] = (
        "F2__value",
        "F2__is_missing",
        "F2__is_not_applicable",
    )
    attack["model_input_dimension"] = 3
    attack["blocker_codes"] = ()
    attack["status"] = CoreFeatureViewStatus.READY
    body = {key: value for key, value in attack.items() if key not in {"view_id", "content_hash"}}
    attack_hash = research_hash({"schema": "core-feature-view-manifest-v1", **body})
    attack["view_id"] = f"core-feature-view:{attack_hash.removeprefix('sha256:')}"
    attack["content_hash"] = attack_hash
    rehashed_view = CoreFeatureViewManifest.model_validate(attack)
    with pytest.raises(ValueError, match="validated parent"):
        project_core_feature_matrix(
            envelope=envelopes[0],
            view=rehashed_view,
            panel_manifest=panel,
            processed_envelopes=envelopes,
            selection_manifest=empty_selection,
        )

    alternate_selection = frozen_selection(
        panel=panel,
        envelopes=envelopes,
        p_values=(0.20, 0.01),
    )
    original_selected = build_core_feature_view_manifest(
        panel_manifest=panel,
        processed_envelopes=envelopes,
        selection_manifest=frozen_selection(
            panel=panel,
            envelopes=envelopes,
            p_values=(0.01, 0.20),
        ),
        view_kind=CoreFeatureViewKind.SELECTED,
    )
    with pytest.raises(ValueError, match="validated parent"):
        project_core_feature_matrix(
            envelope=envelopes[0],
            view=original_selected,
            panel_manifest=panel,
            processed_envelopes=envelopes,
            selection_manifest=alternate_selection,
        )


def test_rehashed_processed_row_still_rejects_non_finite_observed_value() -> None:
    data = CoreProcessedFeatureRow(
        instrument_id="A",
        feature_id="F",
        feature_definition_version="1.0.0",
        availability_state=FeatureAvailabilityState.OBSERVED,
        value_raw=1.0,
        value_winsorized=1.0,
        value_standardized_observed=1.0,
        model_value=1.0,
        imputation_source=CoreImputationSource.NONE,
        is_missing=False,
        is_not_applicable=False,
    ).model_dump()
    data["model_value"] = math.inf
    with pytest.raises(ValueError, match="finite"):
        CoreProcessedFeatureRow.model_validate(data)
