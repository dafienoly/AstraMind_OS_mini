from __future__ import annotations

from collections.abc import Callable

import pytest
from pydantic import model_serializer
from test_core_feature_selection_attack_support import (
    forged_cluster_representative,
    forged_complete_link_split,
    forged_legacy_receipts,
    forged_turnover,
)
from test_core_feature_selection_production_support import (
    production_selection_case,
    production_selection_parents,
)

from astramind_mini.strategy_research.core.feature_selection import (
    CoreFeatureSelectionManifest,
    CoreFeatureSelectionParents,
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
    parents, selection = production_selection_case(
        PACKAGE,
        CoreLabelHorizon.H20,
        profile="complete_link",
    )
    forged = attack(selection)
    with pytest.raises(ValueError, match="reconstructed true parents"):
        validate_core_feature_selection(forged, parents)


@pytest.mark.parametrize("turnover", (0.5, 0.9))
def test_fully_rehashed_turnover_attack_fails_against_true_parents(
    turnover: float,
) -> None:
    parents, selection = production_selection_case(
        PACKAGE,
        CoreLabelHorizon.H20,
        profile="complete_link",
    )
    forged = forged_turnover(selection, turnover)
    with pytest.raises(ValueError, match="reconstructed true parents"):
        validate_core_feature_selection(forged, parents)


def test_all_legacy_receipt_forgery_shapes_are_rejected_as_candidate_manifests() -> None:
    parents, selection = production_selection_case(
        PACKAGE,
        CoreLabelHorizon.H20,
    )
    forged = forged_turnover(selection, 0.5)
    for attack in forged_legacy_receipts(forged, parents):
        with pytest.raises(TypeError, match="only candidate manifests"):
            validate_core_feature_selection(attack, parents)  # type: ignore[arg-type]


def test_manifest_subclass_cannot_override_content_comparison() -> None:
    parents, selection = production_selection_case(
        PACKAGE,
        CoreLabelHorizon.H20,
    )
    forged = forged_turnover(selection, 0.5)

    class InstanceHookBypass(CoreFeatureSelectionManifest):
        def __eq__(self, other: object) -> bool:
            del other
            return True

        def model_dump(
            self,
            *args: object,
            **kwargs: object,
        ) -> dict[str, object]:
            del args, kwargs
            return selection.model_dump()

        @model_serializer(mode="plain")
        def serialize_as_expected(self) -> dict[str, object]:
            return selection.model_dump()

    attack = InstanceHookBypass.model_construct(
        **{field: getattr(forged, field) for field in CoreFeatureSelectionManifest.model_fields}
    )
    with pytest.raises(ValueError, match="reconstructed true parents"):
        validate_core_feature_selection(attack, parents)


def test_rebuilt_selection_has_exact_base_canonical_bytes() -> None:
    parents, selection = production_selection_case(
        PACKAGE,
        CoreLabelHorizon.H20,
    )
    rebuilt = validate_core_feature_selection(selection, parents)
    serializer = CoreFeatureSelectionManifest.__pydantic_serializer__
    assert serializer.to_json(selection) == serializer.to_json(rebuilt)


def test_future_source_tail_is_excluded_before_parent_freeze_and_changes_no_identity() -> None:
    parents, selection = production_selection_case(
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
    assert rebuild_core_feature_selection(frozen) == selection
