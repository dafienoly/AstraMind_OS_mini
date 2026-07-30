"""Immutable contracts for reusable definitions and later-period matrices."""

from __future__ import annotations

import math
from datetime import date

from pydantic import Field, model_validator

from astramind_mini.contracts.base import ContentHash, ContractModel, Identifier

from ...application.identity import research_hash
from ..labels import CoreLabelHorizon
from .views import CoreFeatureViewKind, CoreFeatureViewStatus


class CoreFrozenFeatureDefinition(ContractModel):
    definition_id: Identifier
    content_hash: ContentHash
    view_kind: CoreFeatureViewKind
    package_id: Identifier
    horizon: CoreLabelHorizon
    development_selection_manifest_id: Identifier
    development_selection_content_hash: ContentHash
    development_selection_plan_id: Identifier
    development_selection_plan_content_hash: ContentHash
    development_selection_fold_id: Identifier
    development_selection_fold_content_hash: ContentHash
    development_selection_spec_hash: ContentHash
    development_prior_content_hash: ContentHash
    development_prior_tokenizer_rules_hash: ContentHash
    development_panel_manifest_id: Identifier
    development_panel_content_hash: ContentHash
    development_view_id: Identifier
    development_view_content_hash: ContentHash
    development_last_decision_date: date
    definition_registry_hash: ContentHash
    computation_manifest_hash: ContentHash
    processing_spec_hash: ContentHash
    package_feature_order: tuple[Identifier, ...] = Field(min_length=1)
    feature_keys: tuple[Identifier, ...]
    feature_ids: tuple[Identifier, ...]
    model_columns: tuple[Identifier, ...]
    model_input_dimension: int = Field(ge=0)
    status: CoreFeatureViewStatus
    blocker_codes: tuple[Identifier, ...]

    @model_validator(mode="after")
    def validate_identity(self) -> CoreFrozenFeatureDefinition:
        selected_in_order = tuple(
            item for item in self.package_feature_order if item in set(self.feature_ids)
        )
        expected_columns = model_columns(self.feature_ids)
        if (
            len(self.feature_keys) != len(self.feature_ids)
            or len(set(self.feature_keys)) != len(self.feature_keys)
            or self.feature_ids != selected_in_order
            or (
                self.view_kind == CoreFeatureViewKind.FULL
                and self.feature_ids != self.package_feature_order
            )
            or self.model_columns != expected_columns
            or self.model_input_dimension != len(expected_columns)
        ):
            raise ValueError("frozen feature definition columns are not canonical")
        expected_status = (
            CoreFeatureViewStatus.BLOCKED if self.blocker_codes else CoreFeatureViewStatus.READY
        )
        if self.status != expected_status:
            raise ValueError("frozen feature definition status differs from blockers")
        expected_hash = research_hash(definition_payload(self))
        expected_id = f"core-frozen-feature-definition:{expected_hash.removeprefix('sha256:')}"
        if self.content_hash != expected_hash or self.definition_id != expected_id:
            raise ValueError("frozen feature definition canonical identity mismatch")
        return self


class CorePeriodFeatureMatrixProjection(ContractModel):
    projection_id: Identifier
    content_hash: ContentHash
    definition_id: Identifier
    definition_content_hash: ContentHash
    period_panel_manifest_id: Identifier
    period_panel_content_hash: ContentHash
    processed_envelope_id: Identifier
    processed_envelope_content_hash: ContentHash
    decision_date: date
    universe_content_hash: ContentHash
    row_order: tuple[Identifier, ...] = Field(min_length=1)
    column_order: tuple[Identifier, ...] = Field(min_length=1)
    values: tuple[tuple[float, ...], ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_identity(self) -> CorePeriodFeatureMatrixProjection:
        if len(self.values) != len(self.row_order) or any(
            len(row) != len(self.column_order) for row in self.values
        ):
            raise ValueError("period feature matrix shape mismatch")
        if any(not math.isfinite(value) for row in self.values for value in row):
            raise ValueError("period feature matrix must be finite")
        expected_hash = research_hash(period_projection_payload(self))
        expected_id = f"core-period-feature-matrix:{expected_hash.removeprefix('sha256:')}"
        if self.content_hash != expected_hash or self.projection_id != expected_id:
            raise ValueError("period feature matrix canonical identity mismatch")
        return self


def freeze_definition(payload: dict[str, object]) -> CoreFrozenFeatureDefinition:
    content_hash = research_hash(payload)
    return CoreFrozenFeatureDefinition.model_validate(
        {
            "definition_id": (
                f"core-frozen-feature-definition:{content_hash.removeprefix('sha256:')}"
            ),
            "content_hash": content_hash,
            **{key: value for key, value in payload.items() if key != "schema"},
        }
    )


def freeze_period_projection(payload: dict[str, object]) -> CorePeriodFeatureMatrixProjection:
    content_hash = research_hash(payload)
    return CorePeriodFeatureMatrixProjection.model_validate(
        {
            "projection_id": f"core-period-feature-matrix:{content_hash.removeprefix('sha256:')}",
            "content_hash": content_hash,
            **{key: value for key, value in payload.items() if key != "schema"},
        }
    )


def model_columns(feature_ids: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(
        column
        for feature_id in feature_ids
        for column in (
            f"{feature_id}__value",
            f"{feature_id}__is_missing",
            f"{feature_id}__is_not_applicable",
        )
    )


def definition_payload(value: CoreFrozenFeatureDefinition) -> dict[str, object]:
    return _identity_payload("core-frozen-feature-definition-v1", value, "definition_id")


def period_projection_payload(value: CorePeriodFeatureMatrixProjection) -> dict[str, object]:
    return _identity_payload("core-period-feature-matrix-v1", value, "projection_id")


def _identity_payload(schema: str, value: ContractModel, identifier: str) -> dict[str, object]:
    return {
        "schema": schema,
        **{
            key: item
            for key, item in value.model_dump().items()
            if key not in {identifier, "content_hash"}
        },
    }


__all__ = ["CoreFrozenFeatureDefinition", "CorePeriodFeatureMatrixProjection"]
