"""Exact-parent reconstruction of reusable development joint definitions."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from astramind_mini.contracts.base import ContractModel

from ..feature_processing import CoreFeatureViewKind
from ..feature_processing.period_models import CoreFrozenFeatureDefinition
from ..feature_processing.period_projection import (
    _freeze_core_frozen_feature_definition,
)
from ..feature_processing.views import _build_core_feature_view_from_selection
from ..labels import CoreLabelHorizon
from .joint import _build_core_joint_views_from_inputs
from .joint_inputs import _collect_validated_joint_inputs
from .joint_models import (
    CANONICAL_JOINT_PACKAGE_ORDER,
    CoreJointSelectedViewManifest,
)
from .joint_period_models import (
    CoreFrozenJointFeatureDefinition,
    CoreFrozenJointParentDefinition,
    freeze_joint_definition,
)
from .models import CoreFeatureSelectionManifest
from .parent_validation import (
    CoreFeatureSelectionParents,
    validate_core_feature_selection,
)


@dataclass(frozen=True)
class CoreFrozenJointFeatureDefinitionParents:
    horizon: CoreLabelHorizon
    package_ids: tuple[str, ...]
    selections: Mapping[str, CoreFeatureSelectionManifest]
    selection_parents: Mapping[str, CoreFeatureSelectionParents]

    @classmethod
    def freeze(
        cls,
        *,
        horizon: CoreLabelHorizon,
        package_ids: tuple[str, ...],
        selections: Mapping[str, CoreFeatureSelectionManifest],
        selection_parents: Mapping[str, CoreFeatureSelectionParents],
    ) -> CoreFrozenJointFeatureDefinitionParents:
        return cls(horizon, package_ids, dict(selections), dict(selection_parents))


def rebuild_core_frozen_joint_feature_definition(
    parents: CoreFrozenJointFeatureDefinitionParents,
) -> CoreFrozenJointFeatureDefinition:
    definition, _ = _rebuild_joint_definition_context(parents)
    return definition


def validate_core_frozen_joint_feature_definition(
    candidate: CoreFrozenJointFeatureDefinition,
    parents: CoreFrozenJointFeatureDefinitionParents,
) -> CoreFrozenJointFeatureDefinition:
    expected, _ = _rebuild_joint_definition_context(parents)
    _same_bytes(candidate, expected, CoreFrozenJointFeatureDefinition, "frozen joint definition")
    return expected


def _rebuild_joint_definition_context(
    parents: CoreFrozenJointFeatureDefinitionParents,
) -> tuple[CoreFrozenJointFeatureDefinition, dict[str, CoreFrozenFeatureDefinition]]:
    parents = CoreFrozenJointFeatureDefinitionParents.freeze(
        horizon=parents.horizon,
        package_ids=tuple(parents.package_ids),
        selections=parents.selections,
        selection_parents=parents.selection_parents,
    )
    _validate_definition_parent_keys(parents)
    selections = {
        package: validate_core_feature_selection(
            parents.selections[package],
            parents.selection_parents[package],
        )
        for package in CANONICAL_JOINT_PACKAGE_ORDER
    }
    single_definitions = {
        package: _freeze_core_frozen_feature_definition(
            selections[package],
            parents.selection_parents[package],
            CoreFeatureViewKind.SELECTED,
        )
        for package in CANONICAL_JOINT_PACKAGE_ORDER
    }
    single_views = {
        package: _build_core_feature_view_from_selection(
            selection_manifest=selections[package],
            selection_parents=parents.selection_parents[package],
            view_kind=CoreFeatureViewKind.SELECTED,
        )
        for package in CANONICAL_JOINT_PACKAGE_ORDER
    }
    joint_inputs = _collect_validated_joint_inputs(
        package_ids=CANONICAL_JOINT_PACKAGE_ORDER,
        horizon=parents.horizon,
        manifests=tuple(selections[package] for package in CANONICAL_JOINT_PACKAGE_ORDER),
        selection_parents=parents.selection_parents,
        single_views=single_views,
    )
    joint_views = _build_core_joint_views_from_inputs(parents.horizon, joint_inputs)
    view = next(item for item in joint_views if item.package_ids == parents.package_ids)
    return _freeze_definition_from_view(view, single_definitions), single_definitions


def _freeze_definition_from_view(
    view: CoreJointSelectedViewManifest,
    single_definitions: Mapping[str, CoreFrozenFeatureDefinition],
) -> CoreFrozenJointFeatureDefinition:
    payload = {
        "schema": "core-frozen-joint-definition-v1",
        "view_kind": "selected_joint",
        "horizon": view.horizon,
        "package_ids": view.package_ids,
        "development_joint_view_id": view.joint_view_id,
        "development_joint_view_content_hash": view.content_hash,
        "parent_definitions": tuple(
            CoreFrozenJointParentDefinition(
                package_id=package,
                definition_id=single_definitions[package].definition_id,
                definition_content_hash=single_definitions[package].content_hash,
            )
            for package in view.package_ids
        ),
        "parent_selections": view.parent_selections,
        "prior_content_hash": view.prior_content_hash,
        "candidate_parents": view.candidate_parents,
        "pair_correlations": view.pair_correlations,
        "clusters": view.clusters,
        "selected_parents": view.selected_parents,
        "model_columns": view.model_columns,
        "model_input_dimension": view.model_input_dimension,
        "status": view.status,
        "blocker_codes": view.blocker_codes,
    }
    return freeze_joint_definition(payload)


def _validate_definition_parent_keys(
    parents: CoreFrozenJointFeatureDefinitionParents,
) -> None:
    expected = set(CANONICAL_JOINT_PACKAGE_ORDER)
    ordered = tuple(item for item in CANONICAL_JOINT_PACKAGE_ORDER if item in parents.package_ids)
    if (
        len(parents.package_ids) not in {2, 3}
        or parents.package_ids != ordered
        or set(parents.selections) != expected
        or set(parents.selection_parents) != expected
    ):
        raise ValueError("joint definition requires canonical target and all three true parents")


def _same_bytes(
    candidate: object,
    expected: object,
    model: type[ContractModel],
    label: str,
) -> None:
    if not isinstance(candidate, model):
        raise TypeError(f"{label} boundary accepts only its declared contract")
    serializer = model.__pydantic_serializer__
    candidate_bytes = serializer.to_json(candidate)
    model.model_validate_json(candidate_bytes)
    if candidate_bytes != serializer.to_json(expected):
        raise ValueError(f"{label} differs from exact parents")


__all__ = [
    "CoreFrozenJointFeatureDefinitionParents",
    "rebuild_core_frozen_joint_feature_definition",
    "validate_core_frozen_joint_feature_definition",
]
