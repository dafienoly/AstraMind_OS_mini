"""Immutable contracts for selected-only cross-package feature views."""

from __future__ import annotations

from datetime import date
from enum import StrEnum

from pydantic import Field, model_validator

from astramind_mini.contracts.base import ContentHash, ContractModel, Identifier

from ...application.identity import research_hash
from ..labels import CoreLabelHorizon
from ..packages import ASTRAMIND_F0, FORMULAIC_ALPHA101, QLIB_ALPHA158
from .models import CorePairCorrelationEvidence, CoreSelectionCluster

CANONICAL_JOINT_PACKAGE_ORDER = (
    ASTRAMIND_F0.package_id,
    QLIB_ALPHA158.package_id,
    FORMULAIC_ALPHA101.package_id,
)


class CoreJointParentSelection(ContractModel):
    package_id: Identifier
    selection_manifest_id: Identifier
    selection_content_hash: ContentHash
    panel_manifest_id: Identifier
    panel_content_hash: ContentHash
    single_view_id: Identifier
    single_view_content_hash: ContentHash


class CoreJointFeatureParent(ContractModel):
    package_id: Identifier
    feature_key: Identifier
    feature_id: Identifier
    direction_consistent: bool
    complexity: int = Field(ge=1)
    coverage_mean: float | None = Field(default=None, ge=0.0, le=1.0)
    turnover: float | None = Field(default=None, ge=0.0)
    stability: float | None = Field(default=None, ge=0.0, le=1.0)


class CoreJointDailyBinding(ContractModel):
    decision_date: date
    package_envelopes: tuple[tuple[Identifier, Identifier, ContentHash], ...] = Field(
        min_length=2,
        max_length=3,
    )


class CoreJointViewStatus(StrEnum):
    READY = "ready"
    BLOCKED = "blocked"


class CoreJointSelectedViewManifest(ContractModel):
    joint_view_id: Identifier
    content_hash: ContentHash
    view_kind: str
    horizon: CoreLabelHorizon
    package_ids: tuple[Identifier, ...] = Field(min_length=2, max_length=3)
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
    daily_bindings: tuple[CoreJointDailyBinding, ...] = Field(min_length=1)
    excluded_dates: tuple[date, ...]
    status: CoreJointViewStatus
    blocker_codes: tuple[Identifier, ...]

    @model_validator(mode="after")
    def validate_identity(self) -> CoreJointSelectedViewManifest:
        if self.view_kind != "selected_joint":
            raise ValueError("full joint views are forbidden")
        if not self.horizon.selectable:
            raise ValueError("D1/D3/D5 cannot form a joint selected view")
        expected_packages = tuple(
            item for item in CANONICAL_JOINT_PACKAGE_ORDER if item in self.package_ids
        )
        if self.package_ids != expected_packages:
            raise ValueError("joint packages must follow F0/Alpha158/Alpha101 order")
        if tuple(item.package_id for item in self.parent_selections) != self.package_ids:
            raise ValueError("joint parent selections must follow package order")
        candidate_keys = tuple(item.feature_key for item in self.candidate_parents)
        if len(set(candidate_keys)) != len(candidate_keys) or any(
            item.package_id not in self.package_ids for item in self.candidate_parents
        ):
            raise ValueError("joint candidate parents must be unique declared-package features")
        from .joint_validation import validate_joint_evidence

        validate_joint_evidence(self)
        binding_dates = tuple(item.decision_date for item in self.daily_bindings)
        if binding_dates != tuple(sorted(set(binding_dates))) or any(
            tuple(item[0] for item in binding.package_envelopes) != self.package_ids
            for binding in self.daily_bindings
        ):
            raise ValueError("joint daily bindings must be ordered and package-complete")
        expected_columns = tuple(
            column
            for item in self.selected_parents
            for column in (
                f"{item.feature_id}__value",
                f"{item.feature_id}__is_missing",
                f"{item.feature_id}__is_not_applicable",
            )
        )
        if self.model_columns != expected_columns or self.model_input_dimension != len(
            expected_columns
        ):
            raise ValueError("joint selected columns are not canonical")
        expected_status = (
            CoreJointViewStatus.BLOCKED if self.blocker_codes else CoreJointViewStatus.READY
        )
        if self.status != expected_status:
            raise ValueError("joint selected status does not match blockers")
        expected_hash = research_hash(_joint_payload(self))
        expected_id = f"core-joint-selected:{expected_hash.removeprefix('sha256:')}"
        if self.content_hash != expected_hash or self.joint_view_id != expected_id:
            raise ValueError("joint selected manifest canonical identity mismatch")
        return self


def _joint_payload(view: CoreJointSelectedViewManifest) -> dict[str, object]:
    return {
        "schema": "core-joint-selected-view-v1",
        **{
            key: value
            for key, value in view.model_dump().items()
            if key not in {"joint_view_id", "content_hash"}
        },
    }


__all__ = [
    "CANONICAL_JOINT_PACKAGE_ORDER",
    "CoreJointDailyBinding",
    "CoreJointFeatureParent",
    "CoreJointParentSelection",
    "CoreJointSelectedViewManifest",
    "CoreJointViewStatus",
]
