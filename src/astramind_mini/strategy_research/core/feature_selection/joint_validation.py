"""Recompute joint clustering and representative choices from frozen evidence."""

from __future__ import annotations

import itertools
from typing import TYPE_CHECKING

from .clustering import complete_linkage_clusters
from .representative import representative_sort_key

if TYPE_CHECKING:
    from .joint_models import CoreJointSelectedViewManifest


def validate_joint_evidence(view: CoreJointSelectedViewManifest) -> None:
    expected_pairs = tuple(
        tuple(sorted((left.feature_key, right.feature_key)))
        for left, right in itertools.combinations(view.candidate_parents, 2)
        if left.package_id != right.package_id
    )
    actual_pairs = tuple(
        (item.left_feature_key, item.right_feature_key) for item in view.pair_correlations
    )
    if actual_pairs != expected_pairs:
        raise ValueError("joint correlations must cover exact cross-package pairs")
    for item in view.pair_correlations:
        sufficient = item.valid_date_count >= 60
        available = item.status.value == "available"
        expected_distance = (
            1.0 - abs(float(item.median_daily_spearman))
            if item.median_daily_spearman is not None
            else None
        )
        if (
            available != sufficient
            or (item.median_daily_spearman is not None) != sufficient
            or item.distance != expected_distance
        ):
            raise ValueError("joint correlation status or distance is not canonical")
    distances = {
        frozenset((item.left_feature_key, item.right_feature_key)): item.distance
        for item in view.pair_correlations
    }
    candidate_keys = tuple(item.feature_key for item in view.candidate_parents)
    expected_members = complete_linkage_clusters(
        candidate_keys,
        distances,
        maximum_distance=0.15,
    )
    parents_by_key = {item.feature_key: item for item in view.candidate_parents}
    expected_clusters = tuple(
        (
            members,
            min(members, key=lambda key: representative_sort_key(parents_by_key[key])),
        )
        for members in expected_members
    )
    actual_clusters = tuple((item.members, item.representative) for item in view.clusters)
    if actual_clusters != expected_clusters:
        raise ValueError("joint clusters or representatives are not reproducible")
    representatives = {representative for _, representative in expected_clusters}
    expected_selected = tuple(
        item for item in view.candidate_parents if item.feature_key in representatives
    )
    if view.selected_parents != expected_selected:
        raise ValueError("joint selected parents differ from canonical representatives")


__all__ = ["validate_joint_evidence"]
