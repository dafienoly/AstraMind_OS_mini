"""Apply one exact development joint selection to rebuilt later-period panels."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date

from astramind_mini.contracts.base import ContractModel

from ..feature_processing import (
    CoreProcessedFeatureEnvelope,
    CoreProcessedFeaturePanelManifest,
)
from ..feature_processing.parent_validation import (
    CoreProcessedFeaturePanelParents,
    _rebuild_panel_bundle,
)
from ..feature_processing.period_models import CoreFrozenFeatureDefinition
from .joint_models import CoreJointViewStatus
from .joint_period_definition import (
    CoreFrozenJointFeatureDefinitionParents,
    _rebuild_joint_definition_context,
)
from .joint_period_models import (
    CoreFrozenJointFeatureDefinition,
    CorePeriodJointMatrixProjection,
    CorePeriodJointPackageBinding,
    freeze_joint_projection,
)
from .joint_projection import _projection_values


@dataclass(frozen=True)
class CorePeriodJointProjectionParents:
    definition: CoreFrozenJointFeatureDefinition
    definition_parents: CoreFrozenJointFeatureDefinitionParents
    period_panels: Mapping[str, CoreProcessedFeaturePanelManifest]
    period_panel_parents: Mapping[str, CoreProcessedFeaturePanelParents]
    decision_date: date

    @classmethod
    def freeze(
        cls,
        *,
        definition: CoreFrozenJointFeatureDefinition,
        definition_parents: CoreFrozenJointFeatureDefinitionParents,
        period_panels: Mapping[str, CoreProcessedFeaturePanelManifest],
        period_panel_parents: Mapping[str, CoreProcessedFeaturePanelParents],
        decision_date: date,
    ) -> CorePeriodJointProjectionParents:
        return cls(
            definition,
            definition_parents,
            dict(period_panels),
            dict(period_panel_parents),
            decision_date,
        )


def rebuild_core_period_joint_projection(
    parents: CorePeriodJointProjectionParents,
) -> CorePeriodJointMatrixProjection:
    definition, single_definitions = _rebuild_joint_definition_context(parents.definition_parents)
    _same_bytes(
        parents.definition,
        definition,
        CoreFrozenJointFeatureDefinition,
        "frozen joint definition",
    )
    panels, envelopes = _rebuild_period_panels(parents, definition)
    current = _validate_current_joint_inputs(
        definition,
        single_definitions,
        panels,
        envelopes,
        parents.decision_date,
    )
    row_order = next(iter(current.values())).instrument_order
    values = _projection_values(current, definition.selected_parents, row_order)
    bindings = tuple(
        CorePeriodJointPackageBinding(
            package_id=package,
            panel_manifest_id=panels[package].panel_manifest_id,
            panel_content_hash=panels[package].content_hash,
            processed_envelope_id=current[package].envelope_id,
            processed_envelope_content_hash=current[package].content_hash,
            universe_content_hash=current[package].universe_content_hash,
        )
        for package in definition.package_ids
    )
    return freeze_joint_projection(
        {
            "schema": "core-period-joint-matrix-v1",
            "definition_id": definition.definition_id,
            "definition_content_hash": definition.content_hash,
            "decision_date": parents.decision_date,
            "package_bindings": bindings,
            "row_order": row_order,
            "column_order": definition.model_columns,
            "values": values,
        }
    )


def validate_core_period_joint_projection(
    candidate: CorePeriodJointMatrixProjection,
    parents: CorePeriodJointProjectionParents,
) -> CorePeriodJointMatrixProjection:
    expected = rebuild_core_period_joint_projection(parents)
    _same_bytes(candidate, expected, CorePeriodJointMatrixProjection, "period joint projection")
    return expected


def _rebuild_period_panels(
    parents: CorePeriodJointProjectionParents,
    definition: CoreFrozenJointFeatureDefinition,
) -> tuple[
    dict[str, CoreProcessedFeaturePanelManifest],
    dict[str, tuple[CoreProcessedFeatureEnvelope, ...]],
]:
    period_panels = dict(parents.period_panels)
    period_panel_parents = dict(parents.period_panel_parents)
    expected = set(definition.package_ids)
    if set(period_panels) != expected or set(period_panel_parents) != expected:
        raise ValueError("period joint projection requires every and only declared package")
    panels: dict[str, CoreProcessedFeaturePanelManifest] = {}
    envelopes: dict[str, tuple[CoreProcessedFeatureEnvelope, ...]] = {}
    for package in definition.package_ids:
        panel, rebuilt = _rebuild_panel_bundle(period_panel_parents[package])
        if panel.package_id != package or any(
            envelope.package_id != package for envelope in rebuilt
        ):
            raise ValueError("period joint mapping key differs from rebuilt package")
        _same_bytes(
            period_panels[package],
            panel,
            CoreProcessedFeaturePanelManifest,
            f"period panel {package}",
        )
        panels[package] = panel
        envelopes[package] = rebuilt
    return panels, envelopes


def _validate_current_joint_inputs(
    definition: CoreFrozenJointFeatureDefinition,
    single_definitions: Mapping[str, CoreFrozenFeatureDefinition],
    panels: Mapping[str, CoreProcessedFeaturePanelManifest],
    envelopes: Mapping[str, tuple[CoreProcessedFeatureEnvelope, ...]],
    decision_date: date,
) -> dict[str, CoreProcessedFeatureEnvelope]:
    if definition.status == CoreJointViewStatus.BLOCKED:
        raise ValueError("blocked frozen joint definition cannot project")
    current: dict[str, CoreProcessedFeatureEnvelope] = {}
    for package in definition.package_ids:
        _validate_package_period(single_definitions[package], panels[package], envelopes[package])
        envelope = next(
            (item for item in envelopes[package] if item.decision_date == decision_date),
            None,
        )
        if envelope is None:
            raise ValueError("joint projection date is absent from an exact package panel")
        current[package] = envelope
    if (
        len({item.instrument_order for item in current.values()}) != 1
        or len({item.universe_content_hash for item in current.values()}) != 1
    ):
        raise ValueError("joint period inputs must share exact U0 identity and row order")
    if any(
        parent.feature_id in current[parent.package_id].blocked_feature_ids
        for parent in definition.selected_parents
    ):
        raise ValueError("joint period projection contains a blocked selected feature")
    return current


def _validate_package_period(
    definition: CoreFrozenFeatureDefinition,
    panel: CoreProcessedFeaturePanelManifest,
    envelopes: tuple[CoreProcessedFeatureEnvelope, ...],
) -> None:
    if (
        not panel.decision_dates
        or panel.decision_dates[0] <= definition.development_last_decision_date
    ):
        raise ValueError("joint period panels must follow the development selection")
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
        raise ValueError("joint period processing semantics differ from development")


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
    "CorePeriodJointProjectionParents",
    "rebuild_core_period_joint_projection",
    "validate_core_period_joint_projection",
]
