"""Direct finite matrix projection for a frozen joint selected view."""

from __future__ import annotations

import math
from collections.abc import Mapping
from datetime import date

from pydantic import Field, model_validator

from astramind_mini.contracts.base import ContentHash, ContractModel, Identifier

from ...application.identity import research_hash
from ..feature_processing import (
    CoreFeatureViewManifest,
    CoreProcessedFeatureEnvelope,
    CoreProcessedFeatureRow,
)
from .joint import build_core_joint_selected_view_manifests
from .joint_models import CoreJointSelectedViewManifest, CoreJointViewStatus
from .models import CoreFeatureSelectionManifest
from .parent_validation import (
    CoreFeatureSelectionParents,
    ValidatedCoreFeatureSelection,
)


class CoreJointMatrixProjection(ContractModel):
    projection_id: Identifier
    content_hash: ContentHash
    joint_view_id: Identifier
    joint_view_content_hash: ContentHash
    decision_date: date
    row_order: tuple[Identifier, ...] = Field(min_length=1)
    column_order: tuple[Identifier, ...] = Field(min_length=1)
    values: tuple[tuple[float, ...], ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_identity(self) -> CoreJointMatrixProjection:
        if len(self.values) != len(self.row_order) or any(
            len(row) != len(self.column_order) for row in self.values
        ):
            raise ValueError("joint matrix projection shape mismatch")
        if any(not math.isfinite(value) for row in self.values for value in row):
            raise ValueError("joint model matrix must be finite")
        expected_hash = research_hash(_projection_payload(self))
        expected_id = f"core-joint-matrix:{expected_hash.removeprefix('sha256:')}"
        if self.content_hash != expected_hash or self.projection_id != expected_id:
            raise ValueError("joint matrix projection canonical identity mismatch")
        return self


def project_core_joint_selected_matrix(
    *,
    envelopes: Mapping[str, CoreProcessedFeatureEnvelope],
    view: CoreJointSelectedViewManifest,
    selections: Mapping[
        str,
        CoreFeatureSelectionManifest | ValidatedCoreFeatureSelection,
    ],
    selection_parents: Mapping[str, CoreFeatureSelectionParents] | None = None,
    single_views: Mapping[str, CoreFeatureViewManifest],
) -> CoreJointMatrixProjection:
    """Project exact view columns; downstream modeling performs no feature work."""
    view, envelopes, decision_date, row_order = _validate_projection_parents(
        envelopes=envelopes,
        view=view,
        selections=selections,
        selection_parents=selection_parents,
        single_views=single_views,
    )
    values = _projection_values(envelopes, view, row_order)
    payload = {
        "schema": "core-joint-matrix-projection-v1",
        "joint_view_id": view.joint_view_id,
        "joint_view_content_hash": view.content_hash,
        "decision_date": decision_date,
        "row_order": row_order,
        "column_order": view.model_columns,
        "values": values,
    }
    content_hash = research_hash(payload)
    return CoreJointMatrixProjection.model_validate(
        {
            "projection_id": f"core-joint-matrix:{content_hash.removeprefix('sha256:')}",
            "content_hash": content_hash,
            **{key: value for key, value in payload.items() if key != "schema"},
        }
    )


def _validate_projection_parents(
    *,
    envelopes: Mapping[str, CoreProcessedFeatureEnvelope],
    view: CoreJointSelectedViewManifest,
    selections: Mapping[
        str,
        CoreFeatureSelectionManifest | ValidatedCoreFeatureSelection,
    ],
    selection_parents: Mapping[str, CoreFeatureSelectionParents] | None,
    single_views: Mapping[str, CoreFeatureViewManifest],
) -> tuple[
    CoreJointSelectedViewManifest,
    dict[str, CoreProcessedFeatureEnvelope],
    date,
    tuple[str, ...],
]:
    rebuilt = build_core_joint_selected_view_manifests(
        horizon=view.horizon,
        selections=selections,
        selection_parents=selection_parents,
        single_views=single_views,
    )
    expected = next(
        (item for item in rebuilt if item.package_ids == view.package_ids),
        None,
    )
    view = CoreJointSelectedViewManifest.model_validate(view.model_dump())
    if expected is None or view != expected:
        raise ValueError("joint view differs from its validated parent objects")
    validated_daily_envelopes = {
        package: _selection_parent_envelopes(
            selections[package],
            selection_parents[package] if selection_parents is not None else None,
        )
        for package in view.package_ids
    }
    envelopes = {
        package: CoreProcessedFeatureEnvelope.model_validate(envelope.model_dump())
        for package, envelope in envelopes.items()
    }
    if set(envelopes) != set(view.package_ids):
        raise ValueError("joint projection requires every and only declared parent package")
    if any(
        envelope not in validated_daily_envelopes[package]
        for package, envelope in envelopes.items()
    ):
        raise ValueError("joint projection envelope is not a validated parent")
    if view.status == CoreJointViewStatus.BLOCKED:
        raise ValueError("blocked joint selected view cannot project a model matrix")
    decision_dates = {item.decision_date for item in envelopes.values()}
    if len(decision_dates) != 1:
        raise ValueError("joint projection parents must share one decision date")
    decision_date = next(iter(decision_dates))
    if decision_date in view.excluded_dates:
        raise ValueError("joint view excludes this no-observed date")
    binding = next(
        (item for item in view.daily_bindings if item.decision_date == decision_date),
        None,
    )
    if binding is None or any(
        (
            package,
            envelopes[package].envelope_id,
            envelopes[package].content_hash,
        )
        not in binding.package_envelopes
        for package in view.package_ids
    ):
        raise ValueError("joint envelopes do not match the frozen daily binding")
    row_orders = {item.instrument_order for item in envelopes.values()}
    if len(row_orders) != 1:
        raise ValueError("joint parent U0 row order must exactly match")
    row_order = next(iter(row_orders))
    return view, envelopes, decision_date, row_order


def _selection_parent_envelopes(
    selection: CoreFeatureSelectionManifest | ValidatedCoreFeatureSelection,
    parents: CoreFeatureSelectionParents | None,
) -> tuple[CoreProcessedFeatureEnvelope, ...]:
    from .parent_validation import resolve_validated_core_feature_selection

    return resolve_validated_core_feature_selection(selection, parents).parents.processed_envelopes


def _projection_values(
    envelopes: Mapping[str, CoreProcessedFeatureEnvelope],
    view: CoreJointSelectedViewManifest,
    row_order: tuple[str, ...],
) -> tuple[tuple[float, ...], ...]:
    rows_by_parent = {
        (package, row.instrument_id, row.feature_id): row
        for package, envelope in envelopes.items()
        for row in envelope.rows
    }
    return tuple(
        tuple(
            component
            for parent in view.selected_parents
            for component in _row_components(
                rows_by_parent[(parent.package_id, instrument, parent.feature_id)]
            )
        )
        for instrument in row_order
    )


def _row_components(row: CoreProcessedFeatureRow) -> tuple[float, float, float]:
    value = row.model_value
    if value is None or not math.isfinite(value):
        raise ValueError("joint parent lacks a finite processed model value")
    return float(value), float(row.is_missing), float(row.is_not_applicable)


def _projection_payload(projection: CoreJointMatrixProjection) -> dict[str, object]:
    return {
        "schema": "core-joint-matrix-projection-v1",
        **{
            key: value
            for key, value in projection.model_dump().items()
            if key not in {"projection_id", "content_hash"}
        },
    }


__all__ = ["CoreJointMatrixProjection", "project_core_joint_selected_matrix"]
