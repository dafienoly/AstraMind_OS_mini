"""Frozen full/selected feature views and direct finite matrix projection."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from enum import StrEnum
from typing import TYPE_CHECKING

from pydantic import Field, model_validator

from astramind_mini.contracts.base import ContentHash, ContractModel, Identifier

from ...application.identity import research_hash
from ..labels import CoreLabelHorizon
from .models import CoreCrossSectionStatus, CoreProcessedFeatureEnvelope
from .panel import CoreProcessedFeaturePanelManifest
from .view_lineage import validate_view_panel_envelopes

if TYPE_CHECKING:
    from ..feature_selection.models import CoreFeatureSelectionManifest
    from ..feature_selection.parent_validation import (
        CoreFeatureSelectionParents,
        ValidatedCoreFeatureSelection,
    )


class CoreFeatureViewKind(StrEnum):
    FULL = "full"
    SELECTED = "selected"


class CoreFeatureViewStatus(StrEnum):
    READY = "ready"
    BLOCKED = "blocked"


class CoreViewDailyBinding(ContractModel):
    decision_date: date
    processed_envelope_id: Identifier
    processed_envelope_content_hash: ContentHash
    universe_content_hash: ContentHash


class CoreViewExcludedDate(ContractModel):
    decision_date: date
    reason_codes: tuple[Identifier, ...] = Field(min_length=1)


class CoreFeatureViewManifest(ContractModel):
    view_id: Identifier
    content_hash: ContentHash
    view_kind: CoreFeatureViewKind
    package_id: Identifier
    horizon: CoreLabelHorizon
    panel_manifest_id: Identifier
    panel_content_hash: ContentHash
    selection_manifest_id: Identifier
    selection_content_hash: ContentHash
    feature_keys: tuple[Identifier, ...]
    feature_ids: tuple[Identifier, ...]
    model_columns: tuple[Identifier, ...]
    model_input_dimension: int = Field(ge=0)
    daily_bindings: tuple[CoreViewDailyBinding, ...] = Field(min_length=1)
    excluded_dates: tuple[CoreViewExcludedDate, ...]
    status: CoreFeatureViewStatus
    blocker_codes: tuple[Identifier, ...]

    @model_validator(mode="after")
    def validate_identity(self) -> CoreFeatureViewManifest:
        if not self.horizon.selectable:
            raise ValueError("D1/D3/D5 cannot form a production feature view")
        expected_columns = tuple(
            column
            for feature_id in self.feature_ids
            for column in (
                f"{feature_id}__value",
                f"{feature_id}__is_missing",
                f"{feature_id}__is_not_applicable",
            )
        )
        if (
            len(self.feature_keys) != len(self.feature_ids)
            or len(set(self.feature_keys)) != len(self.feature_keys)
            or len(set(self.feature_ids)) != len(self.feature_ids)
            or self.model_columns != expected_columns
            or self.model_input_dimension != len(expected_columns)
        ):
            raise ValueError("feature view columns or dimensions are not canonical")
        if not self.feature_ids and (
            self.view_kind != CoreFeatureViewKind.SELECTED
            or "selection_empty" not in self.blocker_codes
        ):
            raise ValueError("only a blocked selected view may have no feature columns")
        expected_status = (
            CoreFeatureViewStatus.BLOCKED if self.blocker_codes else CoreFeatureViewStatus.READY
        )
        if self.status != expected_status:
            raise ValueError("feature view status does not match blockers")
        expected_hash = research_hash(_view_payload(self))
        expected_id = f"core-feature-view:{expected_hash.removeprefix('sha256:')}"
        if self.content_hash != expected_hash or self.view_id != expected_id:
            raise ValueError("feature view canonical identity mismatch")
        return self


def build_core_feature_view_manifest(
    *,
    selection_manifest: CoreFeatureSelectionManifest | ValidatedCoreFeatureSelection,
    selection_parents: CoreFeatureSelectionParents | None = None,
    view_kind: CoreFeatureViewKind,
) -> CoreFeatureViewManifest:
    """Freeze a view only after reconstructing selection from every true parent."""
    from ..feature_selection.parent_validation import (
        resolve_validated_core_feature_selection,
    )

    validated = resolve_validated_core_feature_selection(
        selection_manifest,
        selection_parents,
    )
    selection_manifest = validated.manifest
    selection_parents = validated.parents
    panel_manifest = selection_parents.panel_manifest
    _validate_selection_panel(selection_manifest, panel_manifest)
    envelopes = selection_parents.processed_envelopes
    if tuple(item.decision_date for item in envelopes) != tuple(
        sorted(item.decision_date for item in envelopes)
    ):
        raise ValueError("feature view envelopes must preserve parent order")
    validate_view_panel_envelopes(panel_manifest, envelopes)
    feature_keys, feature_ids, blockers = _view_feature_identity(
        panel_manifest,
        selection_manifest,
        view_kind,
    )
    return _freeze_view(
        panel=panel_manifest,
        selection=selection_manifest,
        envelopes=envelopes,
        view_kind=view_kind,
        feature_keys=feature_keys,
        feature_ids=feature_ids,
        blockers=blockers,
    )


def _validate_selection_panel(
    selection: CoreFeatureSelectionManifest,
    panel: CoreProcessedFeaturePanelManifest,
) -> None:
    if (
        selection.package_id != panel.package_id
        or selection.panel_manifest_id != panel.panel_manifest_id
        or selection.panel_content_hash != panel.content_hash
        or selection.feature_order != panel.feature_order
    ):
        raise ValueError("feature view selection and panel identities differ")
    selection_lineage = tuple(
        (
            item.decision_date,
            item.processed_envelope_id,
            item.processed_envelope_content_hash,
            item.universe_content_hash,
        )
        for item in selection.processed_days
    )
    panel_lineage = tuple(
        (
            item.decision_date,
            item.processed_envelope_id,
            item.processed_envelope_content_hash,
            item.universe_content_hash,
        )
        for item in panel.entries
    )
    if selection_lineage != panel_lineage:
        raise ValueError("feature view selection lineage differs from the processed panel")


def _view_feature_identity(
    panel: CoreProcessedFeaturePanelManifest,
    selection: CoreFeatureSelectionManifest,
    view_kind: CoreFeatureViewKind,
) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    evidence = selection.feature_evidence
    if view_kind == CoreFeatureViewKind.FULL:
        feature_ids = panel.feature_order
        feature_keys = tuple(item.feature_key for item in evidence)
        blockers = tuple(
            f"coverage_gate_failed:{item.feature_key}"
            for item in evidence
            if not item.coverage.passed
        )
    else:
        feature_ids = selection.selected_feature_ids
        feature_keys = selection.selected_feature_keys
        blockers = ("selection_empty",) if not feature_ids else ()
    return feature_keys, feature_ids, blockers


def _freeze_view(
    *,
    panel: CoreProcessedFeaturePanelManifest,
    selection: CoreFeatureSelectionManifest,
    envelopes: tuple[CoreProcessedFeatureEnvelope, ...],
    view_kind: CoreFeatureViewKind,
    feature_keys: tuple[str, ...],
    feature_ids: tuple[str, ...],
    blockers: tuple[str, ...],
) -> CoreFeatureViewManifest:
    excluded_dates = _excluded_dates(envelopes, feature_ids)
    bindings = tuple(
        CoreViewDailyBinding(
            decision_date=item.decision_date,
            processed_envelope_id=item.envelope_id,
            processed_envelope_content_hash=item.content_hash,
            universe_content_hash=item.universe_content_hash,
        )
        for item in envelopes
    )
    columns = _model_columns(feature_ids)
    payload = {
        "schema": "core-feature-view-manifest-v1",
        "view_kind": view_kind,
        "package_id": panel.package_id,
        "horizon": selection.horizon,
        "panel_manifest_id": panel.panel_manifest_id,
        "panel_content_hash": panel.content_hash,
        "selection_manifest_id": selection.manifest_id,
        "selection_content_hash": selection.content_hash,
        "feature_keys": feature_keys,
        "feature_ids": feature_ids,
        "model_columns": columns,
        "model_input_dimension": len(columns),
        "daily_bindings": bindings,
        "excluded_dates": excluded_dates,
        "status": (CoreFeatureViewStatus.BLOCKED if blockers else CoreFeatureViewStatus.READY),
        "blocker_codes": blockers,
    }
    content_hash = research_hash(payload)
    return CoreFeatureViewManifest.model_validate(
        {
            "view_id": f"core-feature-view:{content_hash.removeprefix('sha256:')}",
            "content_hash": content_hash,
            **{key: value for key, value in payload.items() if key != "schema"},
        }
    )


def validate_core_feature_view_parents(
    *,
    view: CoreFeatureViewManifest,
    selection_manifest: CoreFeatureSelectionManifest | ValidatedCoreFeatureSelection,
    selection_parents: CoreFeatureSelectionParents | None = None,
) -> tuple[CoreProcessedFeatureEnvelope, ...]:
    """Rebuild a view from validated parents and reject a self-rehashed substitute."""
    from ..feature_selection.parent_validation import (
        resolve_validated_core_feature_selection,
    )

    validated = resolve_validated_core_feature_selection(
        selection_manifest,
        selection_parents,
    )
    view = CoreFeatureViewManifest.model_validate(view.model_dump())
    expected = build_core_feature_view_manifest(
        selection_manifest=validated,
        view_kind=view.view_kind,
    )
    if view != expected:
        raise ValueError("feature view differs from its validated parent objects")
    return validated.parents.processed_envelopes


def _excluded_dates(
    envelopes: Sequence[CoreProcessedFeatureEnvelope],
    feature_ids: Sequence[str],
) -> tuple[CoreViewExcludedDate, ...]:
    return tuple(
        CoreViewExcludedDate(
            decision_date=envelope.decision_date,
            reason_codes=tuple(
                f"no_observed_cross_section:{feature_id}"
                for feature_id in feature_ids
                if next(
                    item for item in envelope.cross_sections if item.feature_id == feature_id
                ).status
                == CoreCrossSectionStatus.NO_OBSERVED
            ),
        )
        for envelope in envelopes
        if any(
            item.feature_id in feature_ids and item.status == CoreCrossSectionStatus.NO_OBSERVED
            for item in envelope.cross_sections
        )
    )


def _model_columns(feature_ids: Sequence[str]) -> tuple[str, ...]:
    return tuple(
        column
        for feature_id in feature_ids
        for column in (
            f"{feature_id}__value",
            f"{feature_id}__is_missing",
            f"{feature_id}__is_not_applicable",
        )
    )


def _view_payload(view: CoreFeatureViewManifest) -> dict[str, object]:
    return {
        "schema": "core-feature-view-manifest-v1",
        **{
            key: value
            for key, value in view.model_dump().items()
            if key not in {"view_id", "content_hash"}
        },
    }


__all__ = [
    "CoreFeatureViewKind",
    "CoreFeatureViewManifest",
    "CoreFeatureViewStatus",
    "CoreViewDailyBinding",
    "CoreViewExcludedDate",
    "build_core_feature_view_manifest",
    "validate_core_feature_view_parents",
]
