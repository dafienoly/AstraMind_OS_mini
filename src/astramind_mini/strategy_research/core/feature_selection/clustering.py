"""Deterministic complete-linkage clustering for redundant factors."""

from __future__ import annotations

from collections.abc import Mapping, Sequence


def complete_linkage_clusters(
    feature_keys: Sequence[str],
    distances: Mapping[frozenset[str], float | None],
    *,
    maximum_distance: float = 0.15,
) -> tuple[tuple[str, ...], ...]:
    """Merge only when every pair is known and the complete-link distance passes."""
    clusters = [tuple([item]) for item in sorted(set(feature_keys))]
    while True:
        candidates: list[tuple[float, tuple[str, ...], tuple[str, ...]]] = []
        for left_index, left in enumerate(clusters):
            for right in clusters[left_index + 1 :]:
                pair_distances = [
                    distances.get(frozenset((left_item, right_item)))
                    for left_item in left
                    for right_item in right
                ]
                if not pair_distances or any(item is None for item in pair_distances):
                    continue
                complete_distance = max(float(item) for item in pair_distances if item is not None)
                if complete_distance <= maximum_distance:
                    candidates.append((complete_distance, left, right))
        if not candidates:
            return tuple(sorted(clusters))
        _, left, right = min(candidates, key=lambda item: (item[0], item[1], item[2]))
        clusters.remove(left)
        clusters.remove(right)
        clusters.append(tuple(sorted((*left, *right))))
        clusters.sort()


__all__ = ["complete_linkage_clusters"]
