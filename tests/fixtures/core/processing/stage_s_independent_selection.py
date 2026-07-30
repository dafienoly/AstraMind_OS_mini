"""Stdlib-only BH, correlation, complete-link and representative replay."""

from __future__ import annotations

import math
from itertools import combinations
from statistics import median


def replay_selection_decisions(
    evidence: list[dict[str, object]],
    entries: list[dict[str, object]],
    daily_profiles: list[tuple[tuple[float | None, ...], ...]],
) -> dict[str, object]:
    """Derive every frozen decision from independently computed evidence."""
    decisions = [dict(item) for item in evidence]
    bh = _benjamini_hochberg(
        {
            str(item["feature_key"]): (
                float(item["bootstrap_p_value"])
                if item["selection_eligible"] and item["bootstrap_p_value"] is not None
                else None
            )
            for item in decisions
        }
    )
    for item in decisions:
        result = bh.get(str(item["feature_key"]))
        item["bh_rank"] = result[0] if result else None
        item["bh_threshold"] = result[1] if result else None
        item["bh_passed"] = bool(result and result[2])
    passed_indices = tuple(index for index, item in enumerate(decisions) if item["bh_passed"])
    correlations = _pair_correlations(decisions, daily_profiles, passed_indices)
    clusters = _complete_linkage(
        tuple(str(decisions[index]["feature_key"]) for index in passed_indices),
        correlations,
    )
    evidence_by_key = {str(item["feature_key"]): item for item in decisions}
    entries_by_key = {str(item["feature_id@definition_version"]): item for item in entries}
    frozen_clusters = [
        {
            "members": list(members),
            "representative": min(
                members,
                key=lambda key: _representative_key(
                    evidence_by_key[key],
                    entries_by_key[key],
                ),
            ),
        }
        for members in clusters
    ]
    selected = {str(item["representative"]) for item in frozen_clusters}
    for item in decisions:
        item["reason_code"] = _reason(item, selected)
    return {
        "feature_evidence": decisions,
        "pair_correlations": correlations,
        "clusters": frozen_clusters,
        "selected_feature_keys": [
            str(item["feature_key"]) for item in decisions if str(item["feature_key"]) in selected
        ],
    }


def _benjamini_hochberg(
    p_values: dict[str, float | None],
    *,
    fdr: float = 0.10,
) -> dict[str, tuple[int, float, bool]]:
    eligible = sorted(
        ((key, value) for key, value in p_values.items() if value is not None),
        key=lambda item: (float(item[1]), item[0]),
    )
    maximum_passing_rank = 0
    for rank, (_, p_value) in enumerate(eligible, start=1):
        if float(p_value) <= rank / len(eligible) * fdr:
            maximum_passing_rank = rank
    return {
        key: (rank, rank / len(eligible) * fdr, rank <= maximum_passing_rank)
        for rank, (key, _) in enumerate(eligible, start=1)
    }


def _pair_correlations(
    evidence: list[dict[str, object]],
    profiles: list[tuple[tuple[float | None, ...], ...]],
    passed_indices: tuple[int, ...],
) -> list[dict[str, object]]:
    correlations: list[dict[str, object]] = []
    for left, right in combinations(passed_indices, 2):
        daily = [
            value
            for day in range(len(profiles[left]))
            if (
                value := _paired_spearman(
                    profiles[left][day],
                    profiles[right][day],
                )
            )
            is not None
        ]
        left_key = str(evidence[left]["feature_key"])
        right_key = str(evidence[right]["feature_key"])
        aggregated = float(median(daily)) if len(daily) >= 60 else None
        correlations.append(
            {
                "left_feature_key": min(left_key, right_key),
                "right_feature_key": max(left_key, right_key),
                "valid_date_count": len(daily),
                "median_daily_spearman": aggregated,
                "distance": 1.0 - abs(aggregated) if aggregated is not None else None,
            }
        )
    return correlations


def _paired_spearman(
    left: tuple[float | None, ...],
    right: tuple[float | None, ...],
) -> float | None:
    pairs = tuple(
        (float(left_value), float(right_value))
        for left_value, right_value in zip(left, right, strict=True)
        if left_value is not None and right_value is not None
    )
    if len(pairs) < 5:
        return None
    return _spearman(
        tuple(item[0] for item in pairs),
        tuple(item[1] for item in pairs),
    )


def _spearman(left: tuple[float, ...], right: tuple[float, ...]) -> float | None:
    left_rank = _average_ranks(left)
    right_rank = _average_ranks(right)
    left_mean = math.fsum(left_rank) / len(left_rank)
    right_mean = math.fsum(right_rank) / len(right_rank)
    numerator = math.fsum(
        (left_value - left_mean) * (right_value - right_mean)
        for left_value, right_value in zip(left_rank, right_rank, strict=True)
    )
    denominator = math.sqrt(
        math.fsum((value - left_mean) ** 2 for value in left_rank)
        * math.fsum((value - right_mean) ** 2 for value in right_rank)
    )
    return numerator / denominator if denominator else None


def _average_ranks(values: tuple[float, ...]) -> tuple[float, ...]:
    ordered = sorted(enumerate(values), key=lambda item: (item[1], item[0]))
    ranks = [0.0] * len(values)
    start = 0
    while start < len(ordered):
        end = start + 1
        while end < len(ordered) and ordered[end][1] == ordered[start][1]:
            end += 1
        rank = (start + 1 + end) / 2.0
        for original, _ in ordered[start:end]:
            ranks[original] = rank
        start = end
    return tuple(ranks)


def _complete_linkage(
    feature_keys: tuple[str, ...],
    correlations: list[dict[str, object]],
) -> tuple[tuple[str, ...], ...]:
    distances = {
        frozenset((str(item["left_feature_key"]), str(item["right_feature_key"]))): item["distance"]
        for item in correlations
    }
    clusters = [tuple([item]) for item in sorted(feature_keys)]
    while True:
        candidates: list[tuple[float, tuple[str, ...], tuple[str, ...]]] = []
        for index, left in enumerate(clusters):
            for right in clusters[index + 1 :]:
                values = [
                    distances.get(frozenset((left_item, right_item)))
                    for left_item in left
                    for right_item in right
                ]
                if values and all(value is not None for value in values):
                    distance = max(float(value) for value in values if value is not None)
                    if distance <= 0.15:
                        candidates.append((distance, left, right))
        if not candidates:
            return tuple(sorted(clusters))
        _, left, right = min(candidates, key=lambda item: (item[0], item[1], item[2]))
        clusters.remove(left)
        clusters.remove(right)
        clusters.append(tuple(sorted((*left, *right))))
        clusters.sort()


def _representative_key(
    evidence: dict[str, object],
    entry: dict[str, object],
) -> tuple[object, ...]:
    coverage = evidence["coverage_mean"]
    turnover = evidence["turnover"]
    stability = evidence["stability"]
    return (
        not bool(evidence["direction_consistent"]),
        int(entry["complexity"]),
        coverage is None,
        -float(coverage or 0.0),
        turnover is None,
        float(turnover or 0.0),
        stability is None,
        -float(stability or 0.0),
        str(evidence["feature_key"]),
    )


def _reason(evidence: dict[str, object], selected: set[str]) -> str:
    if not evidence["coverage_passed"]:
        return "coverage_gate_failed"
    if not evidence["subfold_sample_sufficient"]:
        return "subfold_sample_insufficient"
    if not evidence["selection_eligible"]:
        return "p_value_unavailable"
    if not evidence["bh_passed"]:
        return "bh_rejected"
    return "selected" if str(evidence["feature_key"]) in selected else "cluster_redundant"


__all__ = ["replay_selection_decisions"]
