from __future__ import annotations

from collections.abc import Callable

import pytest
from test_core_feature_selection_attack_support import (
    forged_cluster_representative,
    forged_complete_link_split,
    forged_turnover,
)
from test_core_feature_selection_production_support import (
    production_selection_parents,
    production_validated_selection_case,
)

from astramind_mini.strategy_research.core.feature_selection import (
    CoreFeatureSelectionManifest,
    CoreFeatureSelectionParents,
    ValidatedCoreFeatureSelection,
    rebuild_core_feature_selection,
    validate_core_feature_selection,
)
from astramind_mini.strategy_research.core.labels import CoreLabelHorizon
from astramind_mini.strategy_research.core.packages import ASTRAMIND_F0

PACKAGE = ASTRAMIND_F0.package_id


@pytest.mark.parametrize(
    "attack",
    (
        forged_complete_link_split,
        forged_cluster_representative,
    ),
)
def test_fully_rehashed_selection_evidence_attacks_fail_against_true_parents(
    attack: Callable[
        [CoreFeatureSelectionManifest],
        CoreFeatureSelectionManifest,
    ],
) -> None:
    parents, validated = production_validated_selection_case(
        PACKAGE,
        CoreLabelHorizon.H20,
        profile="complete_link",
    )
    forged = attack(validated.manifest)
    with pytest.raises(ValueError, match="reconstructed true parents"):
        validate_core_feature_selection(forged, parents)


@pytest.mark.parametrize("turnover", (0.5, 0.9))
def test_fully_rehashed_turnover_attack_fails_against_true_parents(
    turnover: float,
) -> None:
    parents, validated = production_validated_selection_case(
        PACKAGE,
        CoreLabelHorizon.H20,
        profile="complete_link",
    )
    forged = forged_turnover(validated.manifest, turnover)
    with pytest.raises(ValueError, match="reconstructed true parents"):
        validate_core_feature_selection(forged, parents)


def test_validated_receipt_cannot_be_publicly_constructed_or_model_validated() -> None:
    parents, validated = production_validated_selection_case(
        PACKAGE,
        CoreLabelHorizon.H20,
    )
    with pytest.raises(TypeError, match="factory-issued"):
        ValidatedCoreFeatureSelection(validated.manifest, parents)
    assert not hasattr(ValidatedCoreFeatureSelection, "model_validate")
    manifest_attribute = "_manifest"
    with pytest.raises(AttributeError, match="immutable"):
        setattr(validated, manifest_attribute, validated.manifest)


def test_future_source_tail_is_excluded_before_parent_freeze_and_changes_no_identity() -> None:
    parents, validated = production_validated_selection_case(
        PACKAGE,
        CoreLabelHorizon.H20,
    )
    shifted = production_selection_parents(
        PACKAGE,
        CoreLabelHorizon.H20,
        fold_offset=1,
    )
    source_envelopes = (*parents.processed_envelopes, shifted.processed_envelopes[-1])
    exact_fold_envelopes = source_envelopes[: len(parents.selection_fold.decision_dates)]
    frozen = CoreFeatureSelectionParents.freeze(
        panel_manifest=parents.panel_manifest,
        processed_envelopes=exact_fold_envelopes,
        label_batches=parents.label_batches,
        selection_plan=parents.selection_plan,
        selection_fold=parents.selection_fold,
        horizon=parents.horizon,
        prior_manifest=parents.prior_manifest,
        selection_spec=parents.selection_spec,
    )
    assert rebuild_core_feature_selection(frozen) == validated.manifest
