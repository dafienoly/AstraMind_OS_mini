from __future__ import annotations

import pytest
from test_core_feature_selection_production_support import (
    production_selection_case,
)

from astramind_mini.strategy_research.core.feature_selection import (
    CoreFeatureSelectionParents,
    load_core_selection_prior_manifest,
    rebuild_core_feature_selection,
    select_core_features,
    validate_core_feature_selection,
)
from astramind_mini.strategy_research.core.labels import CoreLabelHorizon
from astramind_mini.strategy_research.core.packages import ASTRAMIND_F0

PACKAGE = ASTRAMIND_F0.package_id


def test_selector_freezes_h20_and_h60_independently_from_exact_fold_parents() -> None:
    manifests = []
    for horizon in (CoreLabelHorizon.H20, CoreLabelHorizon.H60):
        parents, manifest = production_selection_case(PACKAGE, horizon, profile="golden")
        assert manifest == rebuild_core_feature_selection(parents)
        selected = next(
            item
            for item in manifest.feature_evidence
            if item.feature_id in manifest.selected_feature_ids
        )
        assert selected.bootstrap_p_value == pytest.approx(1 / 10001)
        assert len(manifest.processed_days) == len(manifest.label_batches) == 180
        manifests.append(manifest)
    assert manifests[0].manifest_id != manifests[1].manifest_id
    assert manifests[0].selected_feature_ids != manifests[1].selected_feature_ids


def test_selector_requires_exact_stage_p_prior_plan_and_fold_inputs() -> None:
    parents, manifest = production_selection_case(PACKAGE, CoreLabelHorizon.H20)
    with pytest.raises(ValueError, match="D1/D3/D5"):
        select_core_features(
            panel_manifest=parents.panel_manifest,
            processed_envelopes=parents.processed_envelopes,
            label_batches=parents.label_batches,
            selection_plan=parents.selection_plan,
            fold=parents.selection_fold,
            horizon=CoreLabelHorizon.D1,
            prior_manifest=parents.prior_manifest,
        )

    forged_prior = parents.prior_manifest.model_copy(
        update={"authoritative_source_commit": "forged-source"}
    )
    with pytest.raises(ValueError, match="exact integrated Stage P"):
        select_core_features(
            panel_manifest=parents.panel_manifest,
            processed_envelopes=parents.processed_envelopes,
            label_batches=parents.label_batches,
            selection_plan=parents.selection_plan,
            fold=parents.selection_fold,
            horizon=parents.horizon,
            prior_manifest=forged_prior,
        )

    tail = parents.processed_envelopes[-1].model_copy(
        update={"decision_date": parents.processed_envelopes[-1].decision_date}
    )
    with pytest.raises(ValueError, match="exactly match"):
        select_core_features(
            panel_manifest=parents.panel_manifest,
            processed_envelopes=(*parents.processed_envelopes, tail),
            label_batches=parents.label_batches,
            selection_plan=parents.selection_plan,
            fold=parents.selection_fold,
            horizon=parents.horizon,
            prior_manifest=load_core_selection_prior_manifest(),
        )
    assert validate_core_feature_selection(manifest, parents).manifest == manifest


def test_parent_bundle_order_is_not_silently_normalized() -> None:
    parents, manifest = production_selection_case(PACKAGE, CoreLabelHorizon.H20)
    reversed_parents = CoreFeatureSelectionParents.freeze(
        panel_manifest=parents.panel_manifest,
        processed_envelopes=tuple(reversed(parents.processed_envelopes)),
        label_batches=parents.label_batches,
        selection_plan=parents.selection_plan,
        selection_fold=parents.selection_fold,
        horizon=parents.horizon,
        prior_manifest=parents.prior_manifest,
        selection_spec=parents.selection_spec,
    )
    with pytest.raises(ValueError, match="exactly match"):
        validate_core_feature_selection(manifest, reversed_parents)
