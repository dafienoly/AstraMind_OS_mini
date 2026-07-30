"""Pairwise/triple selected-only joint manifests and finite matrix projection."""

from __future__ import annotations

import itertools
from collections.abc import Mapping
from datetime import date

from ...application.identity import research_hash
from ..feature_processing import (
    CoreFeatureViewManifest,
    CoreProcessedFeatureEnvelope,
)
from ..labels import CoreLabelHorizon
from .clustering import complete_linkage_clusters
from .joint_inputs import JointInputs, collect_joint_inputs
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
    CoreFeatureSelectionManifest,
    CorePairCorrelationEvidence,
    CoreSelectionCluster,
)
from .parent_validation import (
    CoreFeatureSelectionParents,
)
from .representative import representative_sort_key


def build_core_joint_selected_view_manifests(
    *,
    horizon: CoreLabelHorizon,
    selections: Mapping[str, CoreFeatureSelectionManifest],
    selection_parents: Mapping[str, CoreFeatureSelectionParents],
    single_views: Mapping[str, CoreFeatureViewManifest],
) -> tuple[CoreJointSelectedViewManifest, ...]:
    """Publish three pairs and one triple for one horizon."""
    if (
        tuple(package for package in CANONICAL_JOINT_PACKAGE_ORDER if package in selections)
        != CANONICAL_JOINT_PACKAGE_ORDER
    ):
        raise ValueError("joint publication requires exactly all three canonical packages")
    expected_packages = set(CANONICAL_JOINT_PACKAGE_ORDER)
    required_inputs = (selections, single_views)
    if (
        any(set(inputs) != expected_packages for inputs in required_inputs)
        or set(selection_parents) != expected_packages
    ):
        raise ValueError("joint publication cannot omit or add packages")
    validated_inputs = collect_joint_inputs(
        package_ids=CANONICAL_JOINT_PACKAGE_ORDER,
        horizon=horizon,
        selections=selections,
        selection_parents=selection_parents,
        single_views=single_views,
    )
    return _build_core_joint_views_from_inputs(horizon, validated_inputs)


def _build_core_joint_views_from_inputs(
    horizon: CoreLabelHorizon,
    validated_inputs: JointInputs,
) -> tuple[CoreJointSelectedViewManifest, ...]:
    """Build the four canonical views after exact parents were collected once."""
    results = [
        _build_joint(
            package_ids=package_ids,
            horizon=horizon,
            joint_inputs=validated_inputs.subset(package_ids),
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
    joint_inputs: JointInputs,
) -> CoreJointSelectedViewManifest:
    correlations, frozen_clusters, selected_parents = _joint_clusters(joint_inputs)
    selected_manifests = joint_inputs.manifests
    envelopes_by_package = joint_inputs.envelopes_by_package
    parent_selections = _parent_selections(package_ids, joint_inputs)
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


def _parent_selections(
    package_ids: tuple[str, ...],
    inputs: JointInputs,
) -> tuple[CoreJointParentSelection, ...]:
    return tuple(
        CoreJointParentSelection(
            package_id=package,
            selection_manifest_id=manifest.manifest_id,
            selection_content_hash=manifest.content_hash,
            panel_manifest_id=manifest.panel_manifest_id,
            panel_content_hash=manifest.panel_content_hash,
            single_view_id=single_view.view_id,
            single_view_content_hash=single_view.content_hash,
        )
        for package, manifest, single_view in zip(
            package_ids,
            inputs.manifests,
            inputs.single_views,
            strict=True,
        )
    )


def _joint_clusters(
    inputs: JointInputs,
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
                key=lambda key: representative_sort_key(inputs.evidence_by_key[key]),
            ),
        )
        for members in clusters
    )
    representatives = {item.representative for item in frozen_clusters}
    selected_parents = tuple(
        item for item in inputs.candidates if item.feature_key in representatives
    )
    return correlations, frozen_clusters, selected_parents


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


__all__ = ["build_core_joint_selected_view_manifests"]
