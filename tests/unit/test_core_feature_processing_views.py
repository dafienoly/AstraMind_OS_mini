from __future__ import annotations

import math

import pytest
from test_core_feature_selection_production_support import (
    INSTRUMENTS,
    production_validated_selection_case,
)

from astramind_mini.strategy_research.application.identity import research_hash
from astramind_mini.strategy_research.core.feature_processing import (
    CoreFeatureViewKind,
    CoreFeatureViewManifest,
    CoreFeatureViewStatus,
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
from astramind_mini.strategy_research.core.labels import CoreLabelHorizon
from astramind_mini.strategy_research.core.packages import ASTRAMIND_F0

PACKAGE = ASTRAMIND_F0.package_id


def test_full_and_selected_views_bind_real_selection_and_project_fixed_columns() -> None:
    parents, validated = production_validated_selection_case(
        PACKAGE,
        CoreLabelHorizon.H20,
    )
    selection = validated.manifest
    full = build_core_feature_view_manifest(
        selection_manifest=validated,
        view_kind=CoreFeatureViewKind.FULL,
    )
    selected = build_core_feature_view_manifest(
        selection_manifest=validated,
        view_kind=CoreFeatureViewKind.SELECTED,
    )
    assert full.feature_ids == parents.panel_manifest.feature_order
    assert selected.feature_ids == selection.selected_feature_ids
    assert full.status == CoreFeatureViewStatus.BLOCKED
    projection = project_core_feature_matrix(
        envelope=parents.processed_envelopes[0],
        view=selected,
        selection_manifest=validated,
    )
    feature_id = selection.selected_feature_ids[0]
    assert projection.row_order == INSTRUMENTS
    assert projection.column_order == (
        f"{feature_id}__value",
        f"{feature_id}__is_missing",
        f"{feature_id}__is_not_applicable",
    )
    assert projection.values[0] == (0.0, 0.0, 0.0)


def test_empty_selection_and_rehashed_view_fail_closed() -> None:
    empty_parents, empty_validated = production_validated_selection_case(
        PACKAGE,
        CoreLabelHorizon.H20,
        profile="empty",
    )
    empty_view = build_core_feature_view_manifest(
        selection_manifest=empty_validated,
        view_kind=CoreFeatureViewKind.SELECTED,
    )
    assert empty_view.status == CoreFeatureViewStatus.BLOCKED
    assert empty_view.blocker_codes == ("selection_empty",)
    with pytest.raises(ValueError, match="blocked"):
        project_core_feature_matrix(
            envelope=empty_parents.processed_envelopes[0],
            view=empty_view,
            selection_manifest=empty_validated,
        )

    parents, validated = production_validated_selection_case(
        PACKAGE,
        CoreLabelHorizon.H20,
    )
    selected = build_core_feature_view_manifest(
        selection_manifest=validated,
        view_kind=CoreFeatureViewKind.SELECTED,
    )
    attack = selected.model_dump()
    attack["selection_manifest_id"] = "forged-selection"
    forged_view = CoreFeatureViewManifest.model_validate(_rehash_view(attack))
    with pytest.raises(ValueError, match="validated parent"):
        project_core_feature_matrix(
            envelope=parents.processed_envelopes[0],
            view=forged_view,
            selection_manifest=validated,
        )


def test_forged_selection_is_rejected_at_single_view_and_projection_entries() -> None:
    parents, validated = production_validated_selection_case(
        PACKAGE,
        CoreLabelHorizon.H20,
    )
    selection = validated.manifest
    selected = build_core_feature_view_manifest(
        selection_manifest=validated,
        view_kind=CoreFeatureViewKind.SELECTED,
    )
    forged = _selection_with_rehashed_p_value(selection, 0.01)
    with pytest.raises(ValueError, match="reconstructed true parents"):
        build_core_feature_view_manifest(
            selection_manifest=forged,
            selection_parents=parents,
            view_kind=CoreFeatureViewKind.SELECTED,
        )
    with pytest.raises(ValueError, match="reconstructed true parents"):
        project_core_feature_matrix(
            envelope=parents.processed_envelopes[0],
            view=selected,
            selection_manifest=forged,
            selection_parents=parents,
        )


def _selection_with_rehashed_p_value(
    selection: CoreFeatureSelectionManifest,
    p_value: float,
) -> CoreFeatureSelectionManifest:
    data = selection.model_dump()
    evidence = list(data["feature_evidence"])
    selected_index = next(
        index for index, item in enumerate(evidence) if item["bootstrap_p_value"] is not None
    )
    evidence[selected_index] = {
        **evidence[selected_index],
        "bootstrap_p_value": p_value,
    }
    data["feature_evidence"] = tuple(evidence)
    body = {
        key: value for key, value in data.items() if key not in {"manifest_id", "content_hash"}
    }
    content_hash = research_hash(
        {"schema": "core-feature-selection-manifest-v1", **body}
    )
    data["manifest_id"] = f"core-selection:{content_hash.removeprefix('sha256:')}"
    data["content_hash"] = content_hash
    return CoreFeatureSelectionManifest.model_validate(data)


def _rehash_view(data: dict[str, object]) -> dict[str, object]:
    body = {
        key: value for key, value in data.items() if key not in {"view_id", "content_hash"}
    }
    content_hash = research_hash({"schema": "core-feature-view-manifest-v1", **body})
    data["view_id"] = f"core-feature-view:{content_hash.removeprefix('sha256:')}"
    data["content_hash"] = content_hash
    return data


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
