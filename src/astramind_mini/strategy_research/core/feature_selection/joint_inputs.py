"""Validation and collection of exact joint-view parent objects."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from ..feature_processing import (
    CoreFeatureViewKind,
    CoreFeatureViewManifest,
    CoreProcessedFeatureEnvelope,
    CoreProcessedFeaturePanelManifest,
)
from ..feature_processing.views import _build_core_feature_view_from_selection
from ..labels import CoreLabelHorizon
from .joint_models import CoreJointFeatureParent
from .models import CoreFeatureSelectionEvidence, CoreFeatureSelectionManifest
from .parent_validation import (
    CoreFeatureSelectionParents,
    validate_core_feature_selection,
)


@dataclass(frozen=True)
class JointInputs:
    manifests: tuple[CoreFeatureSelectionManifest, ...]
    prior_content_hash: str
    evidence_by_key: dict[str, CoreFeatureSelectionEvidence]
    candidates: tuple[CoreJointFeatureParent, ...]
    envelopes_by_package: dict[str, tuple[CoreProcessedFeatureEnvelope, ...]]
    single_views: tuple[CoreFeatureViewManifest, ...]

    def subset(self, package_ids: tuple[str, ...]) -> JointInputs:
        positions = {manifest.package_id: index for index, manifest in enumerate(self.manifests)}
        return JointInputs(
            manifests=tuple(self.manifests[positions[package]] for package in package_ids),
            prior_content_hash=self.prior_content_hash,
            evidence_by_key=self.evidence_by_key,
            candidates=tuple(item for item in self.candidates if item.package_id in package_ids),
            envelopes_by_package={
                package: self.envelopes_by_package[package] for package in package_ids
            },
            single_views=tuple(self.single_views[positions[package]] for package in package_ids),
        )


def collect_joint_inputs(
    *,
    package_ids: tuple[str, ...],
    horizon: CoreLabelHorizon,
    selections: Mapping[str, CoreFeatureSelectionManifest],
    selection_parents: Mapping[str, CoreFeatureSelectionParents],
    single_views: Mapping[str, CoreFeatureViewManifest],
) -> JointInputs:
    manifests = tuple(
        validate_core_feature_selection(
            selections[package],
            selection_parents[package],
        )
        for package in package_ids
    )
    return _collect_validated_joint_inputs(
        package_ids=package_ids,
        horizon=horizon,
        manifests=manifests,
        selection_parents=selection_parents,
        single_views=single_views,
    )


def _collect_validated_joint_inputs(
    *,
    package_ids: tuple[str, ...],
    horizon: CoreLabelHorizon,
    manifests: tuple[CoreFeatureSelectionManifest, ...],
    selection_parents: Mapping[str, CoreFeatureSelectionParents],
    single_views: Mapping[str, CoreFeatureViewManifest],
) -> JointInputs:
    """Collect after the caller rebuilt each exact selection in this same call."""
    prior_hash = _validate_shared_selection_inputs(manifests, horizon)
    evidence_by_key: dict[str, CoreFeatureSelectionEvidence] = {}
    candidates: list[CoreJointFeatureParent] = []
    envelopes_by_package: dict[str, tuple[CoreProcessedFeatureEnvelope, ...]] = {}
    validated_views: list[CoreFeatureViewManifest] = []
    for package, manifest in zip(package_ids, manifests, strict=True):
        panel, envelopes, view = _validate_package_parents(
            package=package,
            selection=manifest,
            parents=selection_parents[package],
            single_views=single_views,
        )
        del panel
        envelopes_by_package[package] = envelopes
        validated_views.append(view)
        _append_candidates(
            package,
            manifest,
            evidence_by_key,
            candidates,
        )
    validate_joint_daily_calendars(envelopes_by_package)
    return JointInputs(
        manifests=manifests,
        prior_content_hash=prior_hash,
        evidence_by_key=evidence_by_key,
        candidates=tuple(candidates),
        envelopes_by_package=envelopes_by_package,
        single_views=tuple(validated_views),
    )


def _validate_shared_selection_inputs(
    manifests: tuple[CoreFeatureSelectionManifest, ...],
    horizon: CoreLabelHorizon,
) -> str:
    fold_ids = {item.fold.fold_id for item in manifests}
    plan_identities = {
        (item.selection_plan_id, item.selection_plan_content_hash) for item in manifests
    }
    prior_hashes = {item.prior_content_hash for item in manifests}
    spec_hashes = {item.selection_spec_hash for item in manifests}
    label_identities = {
        tuple(
            (item.decision_date, item.batch_id, item.content_hash)
            for item in manifest.label_batches
        )
        for manifest in manifests
    }
    if (
        any(item.horizon != horizon for item in manifests)
        or len(fold_ids) != 1
        or len(plan_identities) != 1
        or len(prior_hashes) != 1
        or len(spec_hashes) != 1
        or len(label_identities) != 1
    ):
        raise ValueError("joint parents must share horizon, fold, labels and prior")
    return next(iter(prior_hashes))


def _validate_package_parents(
    *,
    package: str,
    selection: CoreFeatureSelectionManifest,
    parents: CoreFeatureSelectionParents,
    single_views: Mapping[str, CoreFeatureViewManifest],
) -> tuple[
    CoreProcessedFeaturePanelManifest,
    tuple[CoreProcessedFeatureEnvelope, ...],
    CoreFeatureViewManifest,
]:
    panel = parents.panel_manifest
    envelopes = parents.processed_envelopes
    expected_view = _build_core_feature_view_from_selection(
        selection_manifest=selection,
        selection_parents=parents,
        view_kind=CoreFeatureViewKind.SELECTED,
    )
    actual_view = CoreFeatureViewManifest.model_validate(single_views[package].model_dump())
    if actual_view != expected_view:
        raise ValueError("joint single-package view differs from validated parents")
    actual_lineage = tuple(
        (item.decision_date, item.envelope_id, item.content_hash, item.universe_content_hash)
        for item in envelopes
    )
    expected_lineage = tuple(
        (
            item.decision_date,
            item.processed_envelope_id,
            item.processed_envelope_content_hash,
            item.universe_content_hash,
        )
        for item in selection.processed_days
    )
    if actual_lineage != expected_lineage:
        raise ValueError("joint processed envelopes differ from frozen selection parents")
    return panel, envelopes, actual_view


def _append_candidates(
    package: str,
    manifest: CoreFeatureSelectionManifest,
    evidence_by_key: dict[str, CoreFeatureSelectionEvidence],
    candidates: list[CoreJointFeatureParent],
) -> None:
    manifest_evidence = {item.feature_key: item for item in manifest.feature_evidence}
    for feature_key, feature_id in zip(
        manifest.selected_feature_keys,
        manifest.selected_feature_ids,
        strict=True,
    ):
        if feature_key in evidence_by_key:
            raise ValueError("versioned feature keys must be unique across joint parents")
        evidence = manifest_evidence[feature_key]
        evidence_by_key[feature_key] = evidence
        candidates.append(
            CoreJointFeatureParent(
                package_id=package,
                feature_key=feature_key,
                feature_id=feature_id,
                direction_consistent=evidence.direction_consistent,
                complexity=evidence.complexity,
                coverage_mean=evidence.coverage_mean,
                turnover=evidence.turnover,
                stability=evidence.stability,
            )
        )


def validate_joint_daily_calendars(
    envelopes: Mapping[str, tuple[CoreProcessedFeatureEnvelope, ...]],
) -> None:
    calendars = {
        tuple(item.decision_date for item in package_envelopes)
        for package_envelopes in envelopes.values()
    }
    if len(calendars) != 1:
        raise ValueError("joint parent panels must use exactly the same decision dates")
    for bundles in zip(*envelopes.values(), strict=True):
        if (
            len({item.universe_content_hash for item in bundles}) != 1
            or len({item.instrument_order for item in bundles}) != 1
        ):
            raise ValueError("joint parent panels must share exact daily U0 identities")


__all__ = ["JointInputs", "collect_joint_inputs"]
