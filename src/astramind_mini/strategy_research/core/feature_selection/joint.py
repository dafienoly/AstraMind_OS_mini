"""Pairwise/triple selected-only joint manifests and finite matrix projection."""

from __future__ import annotations

import itertools
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date

from ...application.identity import research_hash
from ..feature_processing import CoreProcessedFeatureEnvelope
from ..labels import CoreLabelHorizon
from .clustering import complete_linkage_clusters
from .joint_models import (
    CANONICAL_JOINT_PACKAGE_ORDER,
    CoreJointDailyBinding,
    CoreJointFeatureParent,
    CoreJointParentSelection,
    CoreJointSelectedViewManifest,
    CoreJointViewStatus,
)
from .metrics import correlation_distance_map, pair_correlation_evidence
from .models import (
    CoreFeatureSelectionEvidence,
    CoreFeatureSelectionManifest,
    CorePairCorrelationEvidence,
    CoreSelectionCluster,
)


@dataclass(frozen=True)
class _JointInputs:
    manifests: tuple[CoreFeatureSelectionManifest, ...]
    prior_content_hash: str
    evidence_by_key: dict[str, CoreFeatureSelectionEvidence]
    candidates: tuple[CoreJointFeatureParent, ...]
    envelopes_by_package: dict[str, tuple[CoreProcessedFeatureEnvelope, ...]]


def build_core_joint_selected_view_manifests(
    *,
    horizon: CoreLabelHorizon,
    selections: Mapping[str, CoreFeatureSelectionManifest],
    processed_envelopes: Mapping[str, Sequence[CoreProcessedFeatureEnvelope]],
) -> tuple[CoreJointSelectedViewManifest, ...]:
    """Publish three pairs and one triple for one horizon."""
    if (
        tuple(package for package in CANONICAL_JOINT_PACKAGE_ORDER if package in selections)
        != CANONICAL_JOINT_PACKAGE_ORDER
    ):
        raise ValueError("joint publication requires exactly all three canonical packages")
    if set(selections) != set(CANONICAL_JOINT_PACKAGE_ORDER) or set(processed_envelopes) != set(
        CANONICAL_JOINT_PACKAGE_ORDER
    ):
        raise ValueError("joint publication cannot omit or add packages")
    results = [
        _build_joint(
            package_ids=package_ids,
            horizon=horizon,
            selections=selections,
            processed_envelopes=processed_envelopes,
        )
        for width in (2, 3)
        for package_ids in itertools.combinations(CANONICAL_JOINT_PACKAGE_ORDER, width)
    ]
    if len(results) != 4:
        raise AssertionError("each horizon must publish three pairs and one triple")
    return tuple(results)


def _build_joint(
    *,
    package_ids: tuple[str, ...],
    horizon: CoreLabelHorizon,
    selections: Mapping[str, CoreFeatureSelectionManifest],
    processed_envelopes: Mapping[str, Sequence[CoreProcessedFeatureEnvelope]],
) -> CoreJointSelectedViewManifest:
    joint_inputs = _collect_joint_inputs(
        package_ids=package_ids,
        horizon=horizon,
        selections=selections,
        processed_envelopes=processed_envelopes,
    )
    correlations, frozen_clusters, selected_parents = _joint_clusters(joint_inputs)
    selected_manifests = joint_inputs.manifests
    envelopes_by_package = joint_inputs.envelopes_by_package
    parent_selections = tuple(
        CoreJointParentSelection(
            package_id=package,
            selection_manifest_id=manifest.manifest_id,
            selection_content_hash=manifest.content_hash,
            panel_manifest_id=manifest.panel_manifest_id,
            panel_content_hash=manifest.panel_content_hash,
        )
        for package, manifest in zip(package_ids, selected_manifests, strict=True)
    )
    daily_bindings, excluded_dates = _joint_daily_bindings(
        envelopes_by_package,
        selected_parents,
    )
    blockers = tuple(
        f"selection_empty:{package}"
        for package, manifest in zip(package_ids, selected_manifests, strict=True)
        if not manifest.selected_feature_ids
    )
    columns = tuple(
        column
        for item in selected_parents
        for column in (
            f"{item.feature_id}__value",
            f"{item.feature_id}__is_missing",
            f"{item.feature_id}__is_not_applicable",
        )
    )
    payload = {
        "schema": "core-joint-selected-view-v1",
        "view_kind": "selected_joint",
        "horizon": horizon,
        "package_ids": package_ids,
        "parent_selections": parent_selections,
        "prior_content_hash": joint_inputs.prior_content_hash,
        "candidate_parents": joint_inputs.candidates,
        "pair_correlations": correlations,
        "clusters": frozen_clusters,
        "selected_parents": selected_parents,
        "model_columns": columns,
        "model_input_dimension": len(columns),
        "daily_bindings": daily_bindings,
        "excluded_dates": excluded_dates,
        "status": (CoreJointViewStatus.BLOCKED if blockers else CoreJointViewStatus.READY),
        "blocker_codes": blockers,
    }
    content_hash = research_hash(payload)
    return CoreJointSelectedViewManifest.model_validate(
        {
            "joint_view_id": (f"core-joint-selected:{content_hash.removeprefix('sha256:')}"),
            "content_hash": content_hash,
            **{key: value for key, value in payload.items() if key != "schema"},
        }
    )


def _joint_clusters(
    inputs: _JointInputs,
) -> tuple[
    tuple[CorePairCorrelationEvidence, ...],
    tuple[CoreSelectionCluster, ...],
    tuple[CoreJointFeatureParent, ...],
]:
    correlations = tuple(
        pair_correlation_evidence(
            left_feature_key=left.feature_key,
            right_feature_key=right.feature_key,
            left_feature_id=left.feature_id,
            right_feature_id=right.feature_id,
            left_envelopes=inputs.envelopes_by_package[left.package_id],
            right_envelopes=inputs.envelopes_by_package[right.package_id],
        )
        for left, right in itertools.combinations(inputs.candidates, 2)
        if left.package_id != right.package_id
    )
    clusters = complete_linkage_clusters(
        tuple(item.feature_key for item in inputs.candidates),
        correlation_distance_map(correlations),
    )
    frozen_clusters = tuple(
        CoreSelectionCluster(
            members=members,
            representative=min(
                members,
                key=lambda key: _representative_key(inputs.evidence_by_key[key]),
            ),
        )
        for members in clusters
    )
    representatives = {item.representative for item in frozen_clusters}
    selected_parents = tuple(
        item for item in inputs.candidates if item.feature_key in representatives
    )
    return correlations, frozen_clusters, selected_parents


def _collect_joint_inputs(
    *,
    package_ids: tuple[str, ...],
    horizon: CoreLabelHorizon,
    selections: Mapping[str, CoreFeatureSelectionManifest],
    processed_envelopes: Mapping[str, Sequence[CoreProcessedFeatureEnvelope]],
) -> _JointInputs:
    manifests = tuple(selections[package] for package in package_ids)
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
    evidence_by_key: dict[str, CoreFeatureSelectionEvidence] = {}
    candidates: list[CoreJointFeatureParent] = []
    envelopes_by_package: dict[str, tuple[CoreProcessedFeatureEnvelope, ...]] = {}
    for package, manifest in zip(package_ids, manifests, strict=True):
        envelopes = tuple(sorted(processed_envelopes[package], key=lambda item: item.decision_date))
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
        envelopes_by_package[package] = envelopes
        manifest_evidence = {item.feature_key: item for item in manifest.feature_evidence}
        for feature_key, feature_id in zip(
            manifest.selected_feature_keys,
            manifest.selected_feature_ids,
            strict=True,
        ):
            if feature_key in evidence_by_key:
                raise ValueError("versioned feature keys must be unique across joint parents")
            evidence_by_key[feature_key] = manifest_evidence[feature_key]
            candidates.append(
                CoreJointFeatureParent(
                    package_id=package,
                    feature_key=feature_key,
                    feature_id=feature_id,
                )
            )
    _validate_joint_daily_calendars(envelopes_by_package)
    return _JointInputs(
        manifests=manifests,
        prior_content_hash=next(iter(prior_hashes)),
        evidence_by_key=evidence_by_key,
        candidates=tuple(candidates),
        envelopes_by_package=envelopes_by_package,
    )


def _validate_joint_daily_calendars(
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


def _joint_daily_bindings(
    envelopes: Mapping[str, tuple[CoreProcessedFeatureEnvelope, ...]],
    parents: tuple[CoreJointFeatureParent, ...],
) -> tuple[tuple[CoreJointDailyBinding, ...], tuple[date, ...]]:
    by_package_date = {
        (package, envelope.decision_date): envelope
        for package, package_envelopes in envelopes.items()
        for envelope in package_envelopes
    }
    dates = tuple(item.decision_date for item in next(iter(envelopes.values())))
    bindings = tuple(
        CoreJointDailyBinding(
            decision_date=day,
            package_envelopes=tuple(
                (
                    package,
                    by_package_date[(package, day)].envelope_id,
                    by_package_date[(package, day)].content_hash,
                )
                for package in envelopes
            ),
        )
        for day in dates
    )
    excluded = tuple(
        day
        for day in dates
        if any(
            parent.feature_id in by_package_date[(parent.package_id, day)].blocked_feature_ids
            for parent in parents
        )
    )
    return bindings, excluded


def _representative_key(evidence: CoreFeatureSelectionEvidence) -> tuple[object, ...]:
    return (
        not evidence.direction_consistent,
        evidence.complexity,
        evidence.coverage_mean is None,
        -(evidence.coverage_mean or 0.0),
        evidence.turnover is None,
        evidence.turnover or 0.0,
        evidence.stability is None,
        -(evidence.stability or 0.0),
        evidence.feature_key,
    )


__all__ = ["build_core_joint_selected_view_manifests"]
