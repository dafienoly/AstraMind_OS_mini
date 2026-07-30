"""Direct finite matrix projection for a frozen single-package view."""

from __future__ import annotations

import math
from collections.abc import Sequence
from datetime import date
from typing import TYPE_CHECKING

from pydantic import Field, model_validator

from astramind_mini.contracts.base import ContentHash, ContractModel, Identifier

from ...application.identity import research_hash
from .models import CoreProcessedFeatureEnvelope, CoreProcessedFeatureRow
from .panel import CoreProcessedFeaturePanelManifest
from .views import (
    CoreFeatureViewManifest,
    CoreFeatureViewStatus,
    validate_core_feature_view_parents,
)

if TYPE_CHECKING:
    from ..feature_selection.models import CoreFeatureSelectionManifest


class CoreFeatureMatrixProjection(ContractModel):
    projection_id: Identifier
    content_hash: ContentHash
    view_id: Identifier
    view_content_hash: ContentHash
    processed_envelope_id: Identifier
    processed_envelope_content_hash: ContentHash
    decision_date: date
    row_order: tuple[Identifier, ...] = Field(min_length=1)
    column_order: tuple[Identifier, ...] = Field(min_length=1)
    values: tuple[tuple[float, ...], ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_identity(self) -> CoreFeatureMatrixProjection:
        if len(self.values) != len(self.row_order) or any(
            len(row) != len(self.column_order) for row in self.values
        ):
            raise ValueError("matrix projection shape mismatch")
        if any(not math.isfinite(value) for row in self.values for value in row):
            raise ValueError("model matrix projection must be finite")
        expected_hash = research_hash(_projection_payload(self))
        expected_id = f"core-feature-matrix:{expected_hash.removeprefix('sha256:')}"
        if self.content_hash != expected_hash or self.projection_id != expected_id:
            raise ValueError("matrix projection canonical identity mismatch")
        return self


def project_core_feature_matrix(
    *,
    envelope: CoreProcessedFeatureEnvelope,
    view: CoreFeatureViewManifest,
    panel_manifest: CoreProcessedFeaturePanelManifest,
    processed_envelopes: Sequence[CoreProcessedFeatureEnvelope],
    selection_manifest: CoreFeatureSelectionManifest,
) -> CoreFeatureMatrixProjection:
    """Materialize the exact finite matrix; downstream modeling performs no processing."""
    validated_envelopes = validate_core_feature_view_parents(
        view=view,
        panel_manifest=panel_manifest,
        processed_envelopes=processed_envelopes,
        selection_manifest=selection_manifest,
    )
    envelope = CoreProcessedFeatureEnvelope.model_validate(envelope.model_dump())
    if envelope not in validated_envelopes:
        raise ValueError("projection envelope is not one of the validated view parents")
    binding = next(
        (item for item in view.daily_bindings if item.decision_date == envelope.decision_date),
        None,
    )
    if (
        binding is None
        or binding.processed_envelope_id != envelope.envelope_id
        or binding.processed_envelope_content_hash != envelope.content_hash
    ):
        raise ValueError("processed envelope is not an exact parent of this feature view")
    if view.status == CoreFeatureViewStatus.BLOCKED:
        raise ValueError("blocked feature view cannot project a model matrix")
    if any(item.decision_date == envelope.decision_date for item in view.excluded_dates):
        raise ValueError("excluded no-observed date cannot project a model matrix")
    rows_by_key = {(item.instrument_id, item.feature_id): item for item in envelope.rows}
    values = tuple(
        tuple(
            component
            for feature_id in view.feature_ids
            for component in _row_components(rows_by_key[(instrument, feature_id)])
        )
        for instrument in envelope.instrument_order
    )
    payload = {
        "schema": "core-feature-matrix-projection-v1",
        "view_id": view.view_id,
        "view_content_hash": view.content_hash,
        "processed_envelope_id": envelope.envelope_id,
        "processed_envelope_content_hash": envelope.content_hash,
        "decision_date": envelope.decision_date,
        "row_order": envelope.instrument_order,
        "column_order": view.model_columns,
        "values": values,
    }
    content_hash = research_hash(payload)
    return CoreFeatureMatrixProjection.model_validate(
        {
            "projection_id": (f"core-feature-matrix:{content_hash.removeprefix('sha256:')}"),
            "content_hash": content_hash,
            **{key: value for key, value in payload.items() if key != "schema"},
        }
    )


def _row_components(row: CoreProcessedFeatureRow) -> tuple[float, float, float]:
    model_value = row.model_value
    if model_value is None or not math.isfinite(model_value):
        raise ValueError("view parent row lacks a finite processed model value")
    return (
        float(model_value),
        float(row.is_missing),
        float(row.is_not_applicable),
    )


def _projection_payload(projection: CoreFeatureMatrixProjection) -> dict[str, object]:
    return {
        "schema": "core-feature-matrix-projection-v1",
        **{
            key: value
            for key, value in projection.model_dump().items()
            if key not in {"projection_id", "content_hash"}
        },
    }


__all__ = ["CoreFeatureMatrixProjection", "project_core_feature_matrix"]
