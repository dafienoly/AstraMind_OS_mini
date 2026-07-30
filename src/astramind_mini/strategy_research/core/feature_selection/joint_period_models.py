"""Stable joint-selected definition and exact later-period matrix contracts."""

from __future__ import annotations

import math
from datetime import date
from typing import Literal

from pydantic import Field, model_validator

from astramind_mini.contracts.base import ContentHash, ContractModel, Identifier

from ...application.identity import research_hash
from ..labels import CoreLabelHorizon
from .joint_models import (
    CANONICAL_JOINT_PACKAGE_ORDER,
    CoreJointFeatureParent,
    CoreJointParentSelection,
    CoreJointViewStatus,
)
from .models import CorePairCorrelationEvidence, CoreSelectionCluster


class CoreFrozenJointParentDefinition(ContractModel):
    package_id: Identifier
    definition_id: Identifier
    definition_content_hash: ContentHash


class CoreFrozenJointFeatureDefinition(ContractModel):
    definition_id: Identifier
    content_hash: ContentHash
    view_kind: Literal["selected_joint"]
    horizon: CoreLabelHorizon
    package_ids: tuple[Identifier, ...] = Field(min_length=2, max_length=3)
    development_joint_view_id: Identifier
    development_joint_view_content_hash: ContentHash
    parent_definitions: tuple[CoreFrozenJointParentDefinition, ...] = Field(
        min_length=2,
        max_length=3,
    )
    parent_selections: tuple[CoreJointParentSelection, ...] = Field(
        min_length=2,
        max_length=3,
    )
    prior_content_hash: ContentHash
    candidate_parents: tuple[CoreJointFeatureParent, ...]
    pair_correlations: tuple[CorePairCorrelationEvidence, ...]
    clusters: tuple[CoreSelectionCluster, ...]
    selected_parents: tuple[CoreJointFeatureParent, ...]
    model_columns: tuple[Identifier, ...]
    model_input_dimension: int = Field(ge=0)
    status: CoreJointViewStatus
    blocker_codes: tuple[Identifier, ...]

    @model_validator(mode="after")
    def validate_identity(self) -> CoreFrozenJointFeatureDefinition:
        expected_packages = tuple(
            item for item in CANONICAL_JOINT_PACKAGE_ORDER if item in self.package_ids
        )
        representatives = {item.representative for item in self.clusters}
        expected_selected = tuple(
            item for item in self.candidate_parents if item.feature_key in representatives
        )
        expected_columns = joint_model_columns(self.selected_parents)
        if (
            self.view_kind != "selected_joint"
            or self.package_ids != expected_packages
            or tuple(item.package_id for item in self.parent_definitions) != self.package_ids
            or tuple(item.package_id for item in self.parent_selections) != self.package_ids
            or len({item.feature_key for item in self.candidate_parents})
            != len(self.candidate_parents)
            or self.selected_parents != expected_selected
            or self.model_columns != expected_columns
            or self.model_input_dimension != len(expected_columns)
        ):
            raise ValueError("frozen joint definition parents or columns are not canonical")
        expected_status = (
            CoreJointViewStatus.BLOCKED if self.blocker_codes else CoreJointViewStatus.READY
        )
        if self.status != expected_status:
            raise ValueError("frozen joint definition status differs from blockers")
        expected_hash = research_hash(joint_definition_payload(self))
        expected_id = f"core-frozen-joint-definition:{expected_hash.removeprefix('sha256:')}"
        if self.content_hash != expected_hash or self.definition_id != expected_id:
            raise ValueError("frozen joint definition canonical identity mismatch")
        return self


class CorePeriodJointPackageBinding(ContractModel):
    package_id: Identifier
    panel_manifest_id: Identifier
    panel_content_hash: ContentHash
    processed_envelope_id: Identifier
    processed_envelope_content_hash: ContentHash
    universe_content_hash: ContentHash


class CorePeriodJointMatrixProjection(ContractModel):
    projection_id: Identifier
    content_hash: ContentHash
    definition_id: Identifier
    definition_content_hash: ContentHash
    decision_date: date
    package_bindings: tuple[CorePeriodJointPackageBinding, ...] = Field(
        min_length=2,
        max_length=3,
    )
    row_order: tuple[Identifier, ...] = Field(min_length=1)
    column_order: tuple[Identifier, ...] = Field(min_length=1)
    values: tuple[tuple[float, ...], ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_identity(self) -> CorePeriodJointMatrixProjection:
        packages = tuple(item.package_id for item in self.package_bindings)
        expected_packages = tuple(
            item for item in CANONICAL_JOINT_PACKAGE_ORDER if item in packages
        )
        if (
            packages != expected_packages
            or len({item.universe_content_hash for item in self.package_bindings}) != 1
        ):
            raise ValueError("period joint package bindings or U0 identities differ")
        if len(self.values) != len(self.row_order) or any(
            len(row) != len(self.column_order) for row in self.values
        ):
            raise ValueError("period joint matrix shape mismatch")
        if any(not math.isfinite(value) for row in self.values for value in row):
            raise ValueError("period joint matrix must be finite")
        expected_hash = research_hash(joint_projection_payload(self))
        expected_id = f"core-period-joint-matrix:{expected_hash.removeprefix('sha256:')}"
        if self.content_hash != expected_hash or self.projection_id != expected_id:
            raise ValueError("period joint matrix canonical identity mismatch")
        return self


def freeze_joint_definition(payload: dict[str, object]) -> CoreFrozenJointFeatureDefinition:
    content_hash = research_hash(payload)
    return CoreFrozenJointFeatureDefinition.model_validate(
        {
            "definition_id": f"core-frozen-joint-definition:{content_hash.removeprefix('sha256:')}",
            "content_hash": content_hash,
            **{key: value for key, value in payload.items() if key != "schema"},
        }
    )


def freeze_joint_projection(payload: dict[str, object]) -> CorePeriodJointMatrixProjection:
    content_hash = research_hash(payload)
    return CorePeriodJointMatrixProjection.model_validate(
        {
            "projection_id": f"core-period-joint-matrix:{content_hash.removeprefix('sha256:')}",
            "content_hash": content_hash,
            **{key: value for key, value in payload.items() if key != "schema"},
        }
    )


def joint_model_columns(
    parents: tuple[CoreJointFeatureParent, ...],
) -> tuple[str, ...]:
    return tuple(
        column
        for item in parents
        for column in (
            f"{item.feature_id}__value",
            f"{item.feature_id}__is_missing",
            f"{item.feature_id}__is_not_applicable",
        )
    )


def joint_definition_payload(value: CoreFrozenJointFeatureDefinition) -> dict[str, object]:
    return _payload("core-frozen-joint-definition-v1", value, "definition_id")


def joint_projection_payload(value: CorePeriodJointMatrixProjection) -> dict[str, object]:
    return _payload("core-period-joint-matrix-v1", value, "projection_id")


def _payload(schema: str, value: ContractModel, identifier: str) -> dict[str, object]:
    return {
        "schema": schema,
        **{
            key: item
            for key, item in value.model_dump().items()
            if key not in {identifier, "content_hash"}
        },
    }


__all__ = [
    "CoreFrozenJointFeatureDefinition",
    "CoreFrozenJointParentDefinition",
    "CorePeriodJointMatrixProjection",
    "CorePeriodJointPackageBinding",
]
