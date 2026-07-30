from __future__ import annotations

from collections.abc import Mapping

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
    CoreProcessedFeatureEnvelope,
    CoreProcessedFeaturePanelManifest,
    build_core_feature_view_manifest,
)
from astramind_mini.strategy_research.core.feature_selection import (
    CoreCorrelationStatus,
    CoreFeatureSelectionManifest,
    CoreJointSelectedViewManifest,
    CoreJointViewStatus,
    build_core_joint_selected_view_manifests,
    pair_correlation_evidence,
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
FEATURES = {
    PACKAGES[0]: "F0_TEST",
    PACKAGES[1]: "A158_TEST",
    PACKAGES[2]: "A101_TEST",
}
INSTRUMENTS = ("A", "B", "C", "D", "E")


def _parents(
    horizon: CoreLabelHorizon,
    *,
    empty_package: str | None = None,
    universe_hashes: Mapping[str, tuple[str, ...]] | None = None,
) -> tuple[
    dict[str, tuple[CoreProcessedFeatureEnvelope, ...]],
    dict[str, CoreProcessedFeaturePanelManifest],
    dict[str, CoreFeatureSelectionManifest],
    dict[str, CoreFeatureViewManifest],
]:
    envelopes = {
        package: frozen_envelopes(
            package_id=package,
            feature_ids=(FEATURES[package],),
            instruments=INSTRUMENTS,
            universe_hashes=(universe_hashes.get(package) if universe_hashes is not None else None),
        )
        for package in PACKAGES
    }
    panels = {package: frozen_panel(envelopes[package]) for package in PACKAGES}
    selections = {
        package: frozen_selection(
            panel=panels[package],
            envelopes=envelopes[package],
            horizon=horizon,
            p_values=((0.20,) if package == empty_package else (0.01,)),
        )
        for package in PACKAGES
    }
    views = {
        package: build_core_feature_view_manifest(
            panel_manifest=panels[package],
            processed_envelopes=envelopes[package],
            selection_manifest=selections[package],
            view_kind=CoreFeatureViewKind.SELECTED,
        )
        for package in PACKAGES
    }
    return envelopes, panels, selections, views


def _build(
    horizon: CoreLabelHorizon,
    parents: tuple[
        dict[str, tuple[CoreProcessedFeatureEnvelope, ...]],
        dict[str, CoreProcessedFeaturePanelManifest],
        dict[str, CoreFeatureSelectionManifest],
        dict[str, CoreFeatureViewManifest],
    ],
) -> tuple[CoreJointSelectedViewManifest, ...]:
    envelopes, panels, selections, views = parents
    return build_core_joint_selected_view_manifests(
        horizon=horizon,
        selections=selections,
        processed_envelopes=envelopes,
        panel_manifests=panels,
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
    envelopes, panels, selections, views = h20_parents
    projection = project_core_joint_selected_matrix(
        envelopes={package: envelopes[package][0] for package in PACKAGES},
        view=triple,
        selections=selections,
        processed_envelopes=envelopes,
        panel_manifests=panels,
        single_views=views,
    )
    assert projection.row_order == INSTRUMENTS
    assert projection.column_order == triple.model_columns
    assert len(projection.values[0]) == triple.model_input_dimension


def test_joint_rejects_tail_append_and_cross_package_daily_u0_mismatch() -> None:
    parents = _parents(CoreLabelHorizon.H20)
    envelopes, panels, selections, views = parents
    appended = dict(envelopes)
    appended[PACKAGES[0]] = frozen_envelopes(
        package_id=PACKAGES[0],
        feature_ids=(FEATURES[PACKAGES[0]],),
        instruments=INSTRUMENTS,
        days=181,
    )
    with pytest.raises(ValueError, match=r"panel entries|validated parents"):
        build_core_joint_selected_view_manifests(
            horizon=CoreLabelHorizon.H20,
            selections=selections,
            processed_envelopes=appended,
            panel_manifests=panels,
            single_views=views,
        )

    common = tuple(research_hash({"u0": index}) for index in range(180))
    corrupt = (research_hash({"corrupt-u0": 0}), *common[1:])
    mismatched = _parents(
        CoreLabelHorizon.H20,
        universe_hashes={
            PACKAGES[0]: common,
            PACKAGES[1]: corrupt,
            PACKAGES[2]: common,
        },
    )
    with pytest.raises(ValueError, match="exact daily U0"):
        _build(CoreLabelHorizon.H20, mismatched)


def test_empty_parent_still_publishes_blocked_joint_identities() -> None:
    parents = _parents(CoreLabelHorizon.H20, empty_package=PACKAGES[0])
    views = _build(CoreLabelHorizon.H20, parents)
    assert len(views) == 4
    assert sum(item.status == CoreJointViewStatus.BLOCKED for item in views) == 3
    blocked = next(item for item in views if item.status == CoreJointViewStatus.BLOCKED)
    envelopes, panels, selections, single_views = parents
    with pytest.raises(ValueError, match="blocked"):
        project_core_joint_selected_matrix(
            envelopes={package: envelopes[package][0] for package in blocked.package_ids},
            view=blocked,
            selections=selections,
            processed_envelopes=envelopes,
            panel_manifests=panels,
            single_views=single_views,
        )


def test_fully_rehashed_joint_parent_and_representative_attacks_are_rejected() -> None:
    parents = _parents(CoreLabelHorizon.H20)
    triple = next(
        item for item in _build(CoreLabelHorizon.H20, parents) if len(item.package_ids) == 3
    )
    envelopes, panels, selections, views = parents
    attack = triple.model_dump()
    parent_selections = list(attack["parent_selections"])
    parent_selections[0] = {
        **parent_selections[0],
        "selection_manifest_id": "forged-selection",
    }
    attack["parent_selections"] = tuple(parent_selections)
    forged = CoreJointSelectedViewManifest.model_validate(_rehash_joint(attack))
    with pytest.raises(ValueError, match="validated parent"):
        project_core_joint_selected_matrix(
            envelopes={package: envelopes[package][0] for package in PACKAGES},
            view=forged,
            selections=selections,
            processed_envelopes=envelopes,
            panel_manifests=panels,
            single_views=views,
        )

    representative_attack = triple.model_dump()
    current = representative_attack["clusters"][0]["representative"]
    candidates = [
        {**item, "complexity": 99} if item["feature_key"] == current else item
        for item in representative_attack["candidate_parents"]
    ]
    replacement = min(item["feature_key"] for item in candidates if item["feature_key"] != current)
    representative_attack["candidate_parents"] = tuple(candidates)
    representative_attack["clusters"] = (
        {
            **representative_attack["clusters"][0],
            "representative": replacement,
        },
    )
    selected_parent = next(item for item in candidates if item["feature_key"] == replacement)
    representative_attack["selected_parents"] = (selected_parent,)
    representative_attack["model_columns"] = tuple(
        f"{selected_parent['feature_id']}__{suffix}"
        for suffix in ("value", "is_missing", "is_not_applicable")
    )
    representative_attack["model_input_dimension"] = 3
    rehashed_representative = CoreJointSelectedViewManifest.model_validate(
        _rehash_joint(representative_attack)
    )
    with pytest.raises(ValueError, match="validated parent"):
        project_core_joint_selected_matrix(
            envelopes={package: envelopes[package][0] for package in PACKAGES},
            view=rehashed_representative,
            selections=selections,
            processed_envelopes=envelopes,
            panel_manifests=panels,
            single_views=views,
        )


def _rehash_joint(data: dict[str, object]) -> dict[str, object]:
    body = {
        key: value for key, value in data.items() if key not in {"joint_view_id", "content_hash"}
    }
    content_hash = research_hash({"schema": "core-joint-selected-view-v1", **body})
    data["joint_view_id"] = f"core-joint-selected:{content_hash.removeprefix('sha256:')}"
    data["content_hash"] = content_hash
    return data


def test_pair_correlation_requires_sixty_valid_daily_cross_sections() -> None:
    envelopes, _, _, _ = _parents(CoreLabelHorizon.H20)
    evidence = pair_correlation_evidence(
        left_feature_key="left@1",
        right_feature_key="right@1",
        left_feature_id=FEATURES[PACKAGES[0]],
        right_feature_id=FEATURES[PACKAGES[1]],
        left_envelopes=envelopes[PACKAGES[0]][:59],
        right_envelopes=envelopes[PACKAGES[1]][:59],
    )
    assert evidence.valid_date_count == 59
    assert evidence.status == CoreCorrelationStatus.CORRELATION_EVIDENCE_INSUFFICIENT
    assert evidence.distance is None
