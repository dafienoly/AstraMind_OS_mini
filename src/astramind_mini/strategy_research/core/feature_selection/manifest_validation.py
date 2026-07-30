"""Independent recomputation of selection evidence and frozen decisions."""

from __future__ import annotations

import itertools
from datetime import date
from itertools import pairwise
from typing import TYPE_CHECKING

from .bh import benjamini_hochberg
from .bootstrap import selection_seed
from .clustering import complete_linkage_clusters
from .representative import representative_sort_key
from .statistics import finite_mean, median_absolute_deviation

if TYPE_CHECKING:
    from .models import CoreFeatureSelectionEvidence, CoreFeatureSelectionManifest


def validate_selection_evidence(manifest: CoreFeatureSelectionManifest) -> None:
    """Recompute every evidence-derived decision without trusting stored summaries."""
    _validate_feature_evidence(manifest)
    passed_keys = _validate_bh(manifest)
    _validate_correlations(manifest, passed_keys)
    _validate_clusters_and_selected(manifest, passed_keys)


def _validate_feature_evidence(manifest: CoreFeatureSelectionManifest) -> None:
    fold_dates = manifest.fold.decision_dates
    expected_transition_dates = tuple(pairwise(fold_dates))
    for item in manifest.feature_evidence:
        if (
            item.coverage.feature_id != item.feature_id
            or item.coverage.feature_definition_version != item.definition_version
            or tuple(row.decision_date for row in item.coverage.daily) != fold_dates
        ):
            raise ValueError("coverage evidence must bind the exact feature and fold calendar")
        if tuple(row.decision_date for row in item.daily_rank_ic) != fold_dates:
            raise ValueError("daily RankIC evidence must cover the exact fold calendar")
        signed_values = tuple(
            float(row.signed_rank_ic)
            for row in item.daily_rank_ic
            if row.signed_rank_ic is not None
        )
        if any(
            row.signed_rank_ic
            != (row.rank_ic * item.expected_direction if row.rank_ic is not None else None)
            for row in item.daily_rank_ic
        ):
            raise ValueError("signed RankIC evidence does not match the frozen direction")
        expected_subfolds = tuple(
            _subfold_summary(
                subfold.subfold_id,
                subfold.decision_dates,
                item,
                manifest.selection_spec.minimum_subfold_valid_rankic,
            )
            for subfold in manifest.fold.subfolds
        )
        actual_subfolds = tuple(
            (
                subfold.subfold_id,
                subfold.valid_count,
                subfold.signed_mean_rank_ic,
                subfold.sample_sufficient,
            )
            for subfold in item.subfolds
        )
        if actual_subfolds != expected_subfolds:
            raise ValueError("subfold RankIC summaries are not canonical")
        direction_consistent = all(
            subfold.sample_sufficient
            and subfold.signed_mean_rank_ic is not None
            and subfold.signed_mean_rank_ic > 0.0
            for subfold in item.subfolds
        )
        eligible = (
            item.coverage.passed
            and all(subfold.sample_sufficient for subfold in item.subfolds)
            and bool(signed_values)
        )
        expected_seed = (
            selection_seed(
                item.feature_id,
                item.definition_version,
                manifest.horizon.value,
                manifest.fold.fold_id,
            )
            if eligible
            else None
        )
        if (
            item.direction_consistent != direction_consistent
            or item.signed_mean_rank_ic != finite_mean(signed_values)
            or item.selection_eligible != (eligible and item.bootstrap_p_value is not None)
            or item.bootstrap_seed != expected_seed
            or item.coverage_mean != item.coverage.mean_qualifying_coverage
        ):
            raise ValueError("feature selection summaries are not reproducible")
        expected_stability = _stability(signed_values)
        if item.stability != expected_stability:
            raise ValueError("feature stability does not match daily RankIC")
        actual_dates = tuple(
            (row.previous_date, row.current_date) for row in item.turnover_transitions
        )
        if actual_dates != expected_transition_dates:
            raise ValueError("turnover transitions must cover every adjacent fold date")


def _subfold_summary(
    subfold_id: str,
    dates: tuple[date, ...],
    evidence: CoreFeatureSelectionEvidence,
    minimum_count: int,
) -> tuple[object, ...]:
    daily = {item.decision_date: item.signed_rank_ic for item in evidence.daily_rank_ic}
    valid_values: list[float] = []
    for day in dates:
        value = daily[day]
        if value is not None:
            valid_values.append(value)
    valid = tuple(valid_values)
    return (
        subfold_id,
        len(valid),
        finite_mean(valid),
        len(valid) >= minimum_count,
    )


def _stability(values: tuple[float, ...]) -> float | None:
    mad = median_absolute_deviation(values)
    return 1.0 / (1.0 + mad) if mad is not None else None


def _validate_bh(manifest: CoreFeatureSelectionManifest) -> tuple[str, ...]:
    expected = benjamini_hochberg(
        {
            item.feature_key: (item.bootstrap_p_value if item.selection_eligible else None)
            for item in manifest.feature_evidence
        },
        fdr=manifest.selection_spec.bh_fdr,
    )
    for item in manifest.feature_evidence:
        result = expected.get(item.feature_key)
        if result is None:
            if item.bh_rank is not None or item.bh_threshold is not None or item.bh_passed:
                raise ValueError("ineligible feature polluted the BH family")
        elif (item.bh_rank, item.bh_threshold, item.bh_passed) != result:
            raise ValueError("selection BH evidence is not canonical")
    return tuple(item.feature_key for item in manifest.feature_evidence if item.bh_passed)


def _validate_correlations(
    manifest: CoreFeatureSelectionManifest,
    passed_keys: tuple[str, ...],
) -> None:
    expected_pairs = tuple(
        tuple(sorted((left, right))) for left, right in itertools.combinations(passed_keys, 2)
    )
    actual_pairs = tuple(
        (item.left_feature_key, item.right_feature_key) for item in manifest.pair_correlations
    )
    if actual_pairs != expected_pairs:
        raise ValueError("selection correlations must cover the exact BH-passed pairs")
    minimum_dates = manifest.selection_spec.correlation_minimum_valid_dates
    for item in manifest.pair_correlations:
        sufficient = item.valid_date_count >= minimum_dates
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
            raise ValueError("pair correlation status or distance is not canonical")


def _validate_clusters_and_selected(
    manifest: CoreFeatureSelectionManifest,
    passed_keys: tuple[str, ...],
) -> None:
    distances = {
        frozenset((item.left_feature_key, item.right_feature_key)): item.distance
        for item in manifest.pair_correlations
    }
    expected_members = complete_linkage_clusters(
        passed_keys,
        distances,
        maximum_distance=manifest.selection_spec.complete_linkage_maximum_distance,
    )
    evidence_by_key = {item.feature_key: item for item in manifest.feature_evidence}
    expected_clusters = tuple(
        (
            members,
            min(members, key=lambda key: representative_sort_key(evidence_by_key[key])),
        )
        for members in expected_members
    )
    actual_clusters = tuple(
        (cluster.members, cluster.representative) for cluster in manifest.clusters
    )
    if actual_clusters != expected_clusters:
        raise ValueError("selection clusters or representatives are not reproducible")
    representatives = {representative for _, representative in expected_clusters}
    expected_selected = tuple(
        item.feature_key
        for item in manifest.feature_evidence
        if item.feature_key in representatives
    )
    selected_by_reason = tuple(
        item.feature_key
        for item in manifest.feature_evidence
        if item.reason_code.value == "selected"
    )
    if (
        manifest.selected_feature_keys != expected_selected
        or selected_by_reason != expected_selected
    ):
        raise ValueError("selected feature keys do not match canonical representatives")
    for item in manifest.feature_evidence:
        expected_reason = _reason(item, representatives)
        if item.reason_code.value != expected_reason:
            raise ValueError("selection reason is not derivable from evidence")
    expected_ids = tuple(evidence_by_key[key].feature_id for key in expected_selected)
    if manifest.selected_feature_ids != expected_ids:
        raise ValueError("selected IDs do not match canonical representatives")


def _reason(evidence: CoreFeatureSelectionEvidence, representatives: set[str]) -> str:
    if not evidence.coverage.passed:
        return "coverage_gate_failed"
    if not all(item.sample_sufficient for item in evidence.subfolds):
        return "subfold_sample_insufficient"
    if not evidence.selection_eligible:
        return "p_value_unavailable"
    if not evidence.bh_passed:
        return "bh_rejected"
    return "selected" if evidence.feature_key in representatives else "cluster_redundant"


__all__ = ["validate_selection_evidence"]
