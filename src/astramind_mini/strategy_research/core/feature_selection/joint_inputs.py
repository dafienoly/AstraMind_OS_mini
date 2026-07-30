"""Validation and collection of exact joint-view parent objects."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from ..feature_processing import (
    CoreFeatureViewKind,
    CoreFeatureViewManifest,
    CoreProcessedFeatureEnvelope,
    CoreProcessedFeaturePanelManifest,
    build_core_feature_view_manifest,
)
from ..labels import CoreLabelHorizon
from .joint_models import CoreJointFeatureParent
from .models import CoreFeatureSelectionEvidence, CoreFeatureSelectionManifest


@dataclass(frozen=True)
class JointInputs:
    manifests: tuple[CoreFeatureSelectionManifest, ...]
    prior_content_hash: str
    evidence_by_key: dict[str, CoreFeatureSelectionEvidence]
    candidates: tuple[CoreJointFeatureParent, ...]
    envelopes_by_package: dict[str, tuple[CoreProcessedFeatureEnvelope, ...]]
    single_views: tuple[CoreFeatureViewManifest, ...]


def collect_joint_inputs(
    *,
    package_ids: tuple[str, ...],
    horizon: CoreLabelHorizon,
    selections: Mapping[str, CoreFeatureSelectionManifest],
    processed_envelopes: Mapping[str, Sequence[CoreProcessedFeatureEnvelope]],
    panel_manifests: Mapping[str, CoreProcessedFeaturePanelManifest],
    single_views: Mapping[str, CoreFeatureViewManifest],
) -> JointInputs:
    manifests = tuple(
        CoreFeatureSelectionManifest.model_validate(selections[package].model_dump())
        for package in package_ids
    )
    prior_hash = _validate_shared_selection_inputs(manifests, horizon)
    evidence_by_key: dict[str, CoreFeatureSelectionEvidence] = {}
    candidates: list[CoreJointFeatureParent] = []
    envelopes_by_package: dict[str, tuple[CoreProcessedFeatureEnvelope, ...]] = {}
    validated_views: list[CoreFeatureViewManifest] = []
    for package, manifest in zip(package_ids, manifests, strict=True):
        panel, envelopes, view = _validate_package_parents(
            package=package,
            manifest=manifest,
            processed_envelopes=processed_envelopes,
            panel_manifests=panel_manifests,
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
    prior_hashes = {item.prior_content_hash for item in manifests}
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
        or len(prior_hashes) != 1
        or len(label_identities) != 1
    ):
        raise ValueError("joint parents must share horizon, fold, labels and prior")
    return next(iter(prior_hashes))


def _validate_package_parents(
    *,
    package: str,
    manifest: CoreFeatureSelectionManifest,
    processed_envelopes: Mapping[str, Sequence[CoreProcessedFeatureEnvelope]],
    panel_manifests: Mapping[str, CoreProcessedFeaturePanelManifest],
    single_views: Mapping[str, CoreFeatureViewManifest],
) -> tuple[
    CoreProcessedFeaturePanelManifest,
    tuple[CoreProcessedFeatureEnvelope, ...],
    CoreFeatureViewManifest,
]:
    panel = CoreProcessedFeaturePanelManifest.model_validate(panel_manifests[package].model_dump())
    envelopes = tuple(
        sorted(
            (
                CoreProcessedFeatureEnvelope.model_validate(item.model_dump())
                for item in processed_envelopes[package]
            ),
            key=lambda item: item.decision_date,
        )
    )
    expected_view = build_core_feature_view_manifest(
        panel_manifest=panel,
        processed_envelopes=envelopes,
        selection_manifest=manifest,
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
        for item in manifest.processed_days
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
