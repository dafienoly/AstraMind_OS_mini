"""Apply one validated development feature definition to exact later-period parents."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING, cast

from astramind_mini.contracts.base import ContractModel

from .models import CoreProcessedFeatureEnvelope
from .panel import CoreProcessedFeaturePanelManifest
from .parent_validation import (
    CoreProcessedFeaturePanelParents,
    _rebuild_panel_bundle,
)
from .period_models import (
    CoreFrozenFeatureDefinition,
    CorePeriodFeatureMatrixProjection,
    freeze_definition,
    freeze_period_projection,
)
from .projection import _projection_values
from .views import (
    CoreFeatureViewKind,
    CoreFeatureViewStatus,
    _build_core_feature_view_from_selection,
)

if TYPE_CHECKING:
    from ..feature_selection.models import CoreFeatureSelectionManifest
    from ..feature_selection.parent_validation import CoreFeatureSelectionParents


@dataclass(frozen=True)
class CoreFrozenFeatureDefinitionParents:
    selection_manifest: CoreFeatureSelectionManifest
    selection_parents: CoreFeatureSelectionParents
    view_kind: CoreFeatureViewKind


@dataclass(frozen=True)
class CorePeriodFeatureProjectionParents:
    definition: CoreFrozenFeatureDefinition
    definition_parents: CoreFrozenFeatureDefinitionParents
    period_panel: CoreProcessedFeaturePanelManifest
    period_panel_parents: CoreProcessedFeaturePanelParents
    decision_date: date


def rebuild_core_frozen_feature_definition(
    parents: CoreFrozenFeatureDefinitionParents,
) -> CoreFrozenFeatureDefinition:
    """Rebuild development selection and freeze only its reusable column meaning."""
    from ..feature_selection.parent_validation import validate_core_feature_selection

    selection = validate_core_feature_selection(
        parents.selection_manifest,
        parents.selection_parents,
    )
    return _freeze_core_frozen_feature_definition(
        selection,
        parents.selection_parents,
        parents.view_kind,
    )


def _freeze_core_frozen_feature_definition(
    selection: CoreFeatureSelectionManifest,
    selection_parents: CoreFeatureSelectionParents,
    view_kind: CoreFeatureViewKind,
) -> CoreFrozenFeatureDefinition:
    """Freeze a definition after this call already rebuilt the selection."""
    view = _build_core_feature_view_from_selection(
        selection_manifest=selection,
        selection_parents=selection_parents,
        view_kind=view_kind,
    )
    envelopes = selection_parents.processed_envelopes
    payload = {
        "schema": "core-frozen-feature-definition-v1",
        "view_kind": view.view_kind,
        "package_id": view.package_id,
        "horizon": view.horizon,
        "development_selection_manifest_id": selection.manifest_id,
        "development_selection_content_hash": selection.content_hash,
        "development_selection_plan_id": selection.selection_plan_id,
        "development_selection_plan_content_hash": selection.selection_plan_content_hash,
        "development_selection_fold_id": selection.fold.fold_id,
        "development_selection_fold_content_hash": selection.fold.content_hash,
        "development_selection_spec_hash": selection.selection_spec_hash,
        "development_prior_content_hash": selection.prior_content_hash,
        "development_prior_tokenizer_rules_hash": selection.prior_tokenizer_rules_hash,
        "development_panel_manifest_id": selection.panel_manifest_id,
        "development_panel_content_hash": selection.panel_content_hash,
        "development_view_id": view.view_id,
        "development_view_content_hash": view.content_hash,
        "development_last_decision_date": selection.fold.decision_dates[-1],
        "definition_registry_hash": _shared(envelopes, "definition_registry_hash"),
        "computation_manifest_hash": _shared(envelopes, "computation_manifest_hash"),
        "processing_spec_hash": _shared(envelopes, "processing_spec_hash"),
        "package_feature_order": selection.feature_order,
        "feature_keys": view.feature_keys,
        "feature_ids": view.feature_ids,
        "model_columns": view.model_columns,
        "model_input_dimension": view.model_input_dimension,
        "status": view.status,
        "blocker_codes": view.blocker_codes,
    }
    return freeze_definition(payload)


def validate_core_frozen_feature_definition(
    candidate: CoreFrozenFeatureDefinition,
    parents: CoreFrozenFeatureDefinitionParents,
) -> CoreFrozenFeatureDefinition:
    expected = rebuild_core_frozen_feature_definition(parents)
    _same_bytes(candidate, expected, CoreFrozenFeatureDefinition, "frozen feature definition")
    return expected


def rebuild_core_period_feature_projection(
    parents: CorePeriodFeatureProjectionParents,
) -> CorePeriodFeatureMatrixProjection:
    definition = validate_core_frozen_feature_definition(
        parents.definition,
        parents.definition_parents,
    )
    panel, envelopes = _rebuild_panel_bundle(parents.period_panel_parents)
    _same_bytes(parents.period_panel, panel, CoreProcessedFeaturePanelManifest, "period panel")
    _validate_period_inputs(definition, panel, envelopes, parents.decision_date)
    envelope = next(item for item in envelopes if item.decision_date == parents.decision_date)
    values = _projection_values(envelope, definition.feature_ids)
    payload = {
        "schema": "core-period-feature-matrix-v1",
        "definition_id": definition.definition_id,
        "definition_content_hash": definition.content_hash,
        "period_panel_manifest_id": panel.panel_manifest_id,
        "period_panel_content_hash": panel.content_hash,
        "processed_envelope_id": envelope.envelope_id,
        "processed_envelope_content_hash": envelope.content_hash,
        "decision_date": envelope.decision_date,
        "universe_content_hash": envelope.universe_content_hash,
        "row_order": envelope.instrument_order,
        "column_order": definition.model_columns,
        "values": values,
    }
    return freeze_period_projection(payload)


def validate_core_period_feature_projection(
    candidate: CorePeriodFeatureMatrixProjection,
    parents: CorePeriodFeatureProjectionParents,
) -> CorePeriodFeatureMatrixProjection:
    expected = rebuild_core_period_feature_projection(parents)
    _same_bytes(candidate, expected, CorePeriodFeatureMatrixProjection, "period projection")
    return expected


def _validate_period_inputs(
    definition: CoreFrozenFeatureDefinition,
    panel: CoreProcessedFeaturePanelManifest,
    envelopes: tuple[CoreProcessedFeatureEnvelope, ...],
    decision_date: date,
) -> None:
    if definition.status == CoreFeatureViewStatus.BLOCKED:
        raise ValueError("blocked frozen feature definition cannot project")
    if (
        not panel.decision_dates
        or panel.decision_dates[0] <= definition.development_last_decision_date
    ):
        raise ValueError("period projection date must follow the development selection")
    if decision_date not in panel.decision_dates:
        raise ValueError("period projection date is absent from the exact panel")
    expected = (
        definition.package_id,
        definition.package_feature_order,
        definition.definition_registry_hash,
        definition.computation_manifest_hash,
        definition.processing_spec_hash,
    )
    if any(
        (
            item.package_id,
            item.feature_order,
            item.definition_registry_hash,
            item.computation_manifest_hash,
            item.processing_spec_hash,
        )
        != expected
        for item in envelopes
    ):
        raise ValueError("period processing semantics differ from the frozen definition")
    current = next(item for item in envelopes if item.decision_date == decision_date)
    if any(item in current.blocked_feature_ids for item in definition.feature_ids):
        raise ValueError("period projection requires observed cross-sections for every feature")


def _shared(envelopes: tuple[CoreProcessedFeatureEnvelope, ...], field: str) -> str:
    values = {getattr(item, field) for item in envelopes}
    if len(values) != 1:
        raise ValueError(f"development processing lineage changes {field}")
    return cast(str, next(iter(values)))


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
    "CoreFrozenFeatureDefinition",
    "CoreFrozenFeatureDefinitionParents",
    "CorePeriodFeatureMatrixProjection",
    "CorePeriodFeatureProjectionParents",
    "rebuild_core_frozen_feature_definition",
    "rebuild_core_period_feature_projection",
    "validate_core_frozen_feature_definition",
    "validate_core_period_feature_projection",
]
