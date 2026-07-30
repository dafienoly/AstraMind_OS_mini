from __future__ import annotations

from collections.abc import Mapping

import pytest
from test_core_feature_selection_attack_support import (
    forged_bootstrap_p_value,
    forged_complete_link_split,
    forged_legacy_receipts,
)
from test_core_feature_selection_production_support import (
    INSTRUMENTS,
    production_selection_case,
)

from astramind_mini.strategy_research.application.identity import research_hash
from astramind_mini.strategy_research.core.feature_processing import (
    CoreFeatureViewKind,
    CoreFeatureViewManifest,
)
from astramind_mini.strategy_research.core.feature_processing.views import (
    _build_core_feature_view_from_selection,
)
from astramind_mini.strategy_research.core.feature_selection import (
    CoreFeatureSelectionManifest,
    CoreFeatureSelectionParents,
    CoreJointSelectedViewManifest,
    CoreJointViewStatus,
    build_core_joint_selected_view_manifests,
    complete_linkage_clusters,
    project_core_joint_selected_matrix,
)
from astramind_mini.strategy_research.core.labels import CoreLabelHorizon
from astramind_mini.strategy_research.core.packages import (
    ASTRAMIND_F0,
    FORMULAIC_ALPHA101,
    QLIB_ALPHA158,
)

PACKAGES = (
    ASTRAMIND_F0.package_id,
    QLIB_ALPHA158.package_id,
    FORMULAIC_ALPHA101.package_id,
)


def _parents(
    horizon: CoreLabelHorizon,
    *,
    empty_package: str | None = None,
) -> tuple[
    dict[str, CoreFeatureSelectionParents],
    dict[str, CoreFeatureSelectionManifest],
    dict[str, CoreFeatureViewManifest],
]:
    cases = {
        package: production_selection_case(
            package,
            horizon,
            profile="empty" if package == empty_package else "single",
        )
        for package in PACKAGES
    }
    parents = {package: case[0] for package, case in cases.items()}
    selections = {package: case[1] for package, case in cases.items()}
    views = {
        package: _build_core_feature_view_from_selection(
            selection_manifest=selections[package],
            selection_parents=parents[package],
            view_kind=CoreFeatureViewKind.SELECTED,
        )
        for package in PACKAGES
    }
    return parents, selections, views


def _build(
    horizon: CoreLabelHorizon,
    parents: tuple[
        dict[str, CoreFeatureSelectionParents],
        dict[str, CoreFeatureSelectionManifest],
        dict[str, CoreFeatureViewManifest],
    ],
) -> tuple[CoreJointSelectedViewManifest, ...]:
    selection_parents, selections, views = parents
    return build_core_joint_selected_view_manifests(
        horizon=horizon,
        selections=selections,
        selection_parents=selection_parents,
        single_views=views,
    )


def test_each_horizon_freezes_four_joint_views_and_projects_direct_matrix() -> None:
    h20_parents = _parents(CoreLabelHorizon.H20)
    h60_parents = _parents(CoreLabelHorizon.H60)
    h20 = _build(CoreLabelHorizon.H20, h20_parents)
    h60 = _build(CoreLabelHorizon.H60, h60_parents)
    assert len(h20) == len(h60) == 4
    assert len({item.joint_view_id for item in (*h20, *h60)}) == 8
    assert all(item.status == CoreJointViewStatus.READY for item in (*h20, *h60))
    triple = next(item for item in h20 if len(item.package_ids) == 3)
    selection_parents, selections, views = h20_parents
    projection = project_core_joint_selected_matrix(
        envelopes={
            package: selection_parents[package].processed_envelopes[0] for package in PACKAGES
        },
        view=triple,
        selections=selections,
        selection_parents=selection_parents,
        single_views=views,
    )
    assert projection.row_order == INSTRUMENTS
    assert projection.column_order == triple.model_columns
    assert len(projection.values[0]) == triple.model_input_dimension


def test_empty_parent_still_publishes_blocked_joint_identities() -> None:
    parents = _parents(CoreLabelHorizon.H20, empty_package=PACKAGES[0])
    views = _build(CoreLabelHorizon.H20, parents)
    assert len(views) == 4
    assert sum(item.status == CoreJointViewStatus.BLOCKED for item in views) == 3
    blocked = next(item for item in views if item.status == CoreJointViewStatus.BLOCKED)
    selection_parents, selections, single_views = parents
    with pytest.raises(ValueError, match="blocked"):
        project_core_joint_selected_matrix(
            envelopes={
                package: selection_parents[package].processed_envelopes[0]
                for package in blocked.package_ids
            },
            view=blocked,
            selections=selections,
            selection_parents=selection_parents,
            single_views=single_views,
        )


def test_forged_selection_stops_at_joint_builder_and_projection_entries() -> None:
    parents = _parents(CoreLabelHorizon.H20)
    selection_parents, selections, views = parents
    triple = next(
        item for item in _build(CoreLabelHorizon.H20, parents) if len(item.package_ids) == 3
    )
    forged: dict[str, CoreFeatureSelectionManifest] = dict(selections)
    forged[PACKAGES[0]] = forged_bootstrap_p_value(selections[PACKAGES[0]])
    with pytest.raises(ValueError, match="reconstructed true parents"):
        build_core_joint_selected_view_manifests(
            horizon=CoreLabelHorizon.H20,
            selections=forged,
            selection_parents=selection_parents,
            single_views=views,
        )
    with pytest.raises(ValueError, match="reconstructed true parents"):
        project_core_joint_selected_matrix(
            envelopes={
                package: selection_parents[package].processed_envelopes[0] for package in PACKAGES
            },
            view=triple,
            selections=forged,
            selection_parents=selection_parents,
            single_views=views,
        )


def test_legacy_receipt_forgery_shapes_cannot_cross_joint_public_boundaries() -> None:
    parents = _parents(CoreLabelHorizon.H20)
    selection_parents, selections, views = parents
    triple = next(
        item for item in _build(CoreLabelHorizon.H20, parents) if len(item.package_ids) == 3
    )
    forged = forged_bootstrap_p_value(selections[PACKAGES[0]])
    for receipt in forged_legacy_receipts(forged, selection_parents[PACKAGES[0]]):
        attacked = dict(selections)
        attacked[PACKAGES[0]] = receipt  # type: ignore[assignment]
        with pytest.raises(TypeError, match="only candidate manifests"):
            build_core_joint_selected_view_manifests(
                horizon=CoreLabelHorizon.H20,
                selections=attacked,
                selection_parents=selection_parents,
                single_views=views,
            )
        with pytest.raises(TypeError, match="only candidate manifests"):
            project_core_joint_selected_matrix(
                envelopes={
                    package: selection_parents[package].processed_envelopes[0]
                    for package in PACKAGES
                },
                view=triple,
                selections=attacked,
                selection_parents=selection_parents,
                single_views=views,
            )


def test_rehashed_selection_correlation_attack_cannot_propagate_to_joint_view() -> None:
    selection_parents, selections, views = _parents(CoreLabelHorizon.H20)
    complete_parents, complete_selection = production_selection_case(
        PACKAGES[0],
        CoreLabelHorizon.H20,
        profile="complete_link",
    )
    selection_parents = {**selection_parents, PACKAGES[0]: complete_parents}
    attacked: dict[str, CoreFeatureSelectionManifest] = {
        **selections,
        PACKAGES[0]: forged_complete_link_split(complete_selection),
    }
    views = {
        **views,
        PACKAGES[0]: _build_core_feature_view_from_selection(
            selection_manifest=complete_selection,
            selection_parents=complete_parents,
            view_kind=CoreFeatureViewKind.SELECTED,
        ),
    }
    with pytest.raises(ValueError, match="reconstructed true parents"):
        build_core_joint_selected_view_manifests(
            horizon=CoreLabelHorizon.H20,
            selections=attacked,
            selection_parents=selection_parents,
            single_views=views,
        )


def test_fully_rehashed_joint_manifest_is_rejected_against_true_parents() -> None:
    parents = _parents(CoreLabelHorizon.H20)
    triple = next(
        item for item in _build(CoreLabelHorizon.H20, parents) if len(item.package_ids) == 3
    )
    attack = triple.model_dump()
    attack["parent_selections"] = tuple(
        {**item, "selection_manifest_id": "forged-selection"} if index == 0 else item
        for index, item in enumerate(attack["parent_selections"])
    )
    forged = CoreJointSelectedViewManifest.model_validate(_rehash_joint(attack))
    selection_parents, selections, views = parents
    with pytest.raises(ValueError, match="validated parent"):
        project_core_joint_selected_matrix(
            envelopes={
                package: selection_parents[package].processed_envelopes[0] for package in PACKAGES
            },
            view=forged,
            selections=selections,
            selection_parents=selection_parents,
            single_views=views,
        )


def test_complete_linkage_does_not_chain_merge_bridge_correlations() -> None:
    distances: Mapping[frozenset[str], float] = {
        frozenset(("A", "B")): 1.0 - 0.9428571428571428,
        frozenset(("B", "C")): 1.0 - 0.9428571428571428,
        frozenset(("A", "C")): 1.0 - 0.8285714285714286,
    }
    assert complete_linkage_clusters(
        ("A", "B", "C"),
        distances,
        maximum_distance=0.15,
    ) == (("A", "B"), ("C",))

    _, selection = production_selection_case(
        PACKAGES[0],
        CoreLabelHorizon.H20,
        profile="complete_link",
    )
    correlations = {
        frozenset((item.left_feature_key, item.right_feature_key)): item.median_daily_spearman
        for item in selection.pair_correlations
    }
    assert tuple(correlations.values()) == pytest.approx(
        (0.9428571428571428, 0.8285714285714286, 0.9428571428571428)
    )
    assert tuple(item.members for item in selection.clusters) == (
        ("BP@1.0.0", "EP_TTM@1.0.0"),
        ("SP_TTM@1.0.0",),
    )


def _rehash_joint(data: dict[str, object]) -> dict[str, object]:
    body = {
        key: value for key, value in data.items() if key not in {"joint_view_id", "content_hash"}
    }
    content_hash = research_hash({"schema": "core-joint-selected-view-v1", **body})
    data["joint_view_id"] = f"core-joint-selected:{content_hash.removeprefix('sha256:')}"
    data["content_hash"] = content_hash
    return data
