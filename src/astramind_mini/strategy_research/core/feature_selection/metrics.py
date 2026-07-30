"""Panel metrics used by both within-package and joint selection."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from itertools import pairwise
from statistics import median

from ..feature_processing import CoreProcessedFeatureEnvelope
from ..feature_values import FeatureAvailabilityState
from .models import CoreCorrelationStatus, CorePairCorrelationEvidence
from .statistics import average_ranks, spearman_by_key


def observed_feature_map(
    envelope: CoreProcessedFeatureEnvelope,
    feature_id: str,
) -> dict[str, float]:
    return {
        item.instrument_id: float(item.value_standardized_observed)
        for item in envelope.rows
        if item.feature_id == feature_id
        and item.availability_state == FeatureAvailabilityState.OBSERVED
        and item.value_standardized_observed is not None
    }


def feature_turnover(
    envelopes: Sequence[CoreProcessedFeatureEnvelope],
    *,
    feature_id: str,
    minimum_common: int = 5,
    minimum_transitions: int = 60,
) -> tuple[float | None, int]:
    daily_percentiles: list[dict[str, float]] = []
    for envelope in sorted(envelopes, key=lambda item: item.decision_date):
        values = observed_feature_map(envelope, feature_id)
        ordered = sorted(values)
        if len(ordered) < 2:
            daily_percentiles.append({})
            continue
        ranks = average_ranks(tuple(values[item] for item in ordered))
        daily_percentiles.append(
            {
                instrument: (rank - 1.0) / (len(ordered) - 1)
                for instrument, rank in zip(ordered, ranks, strict=True)
            }
        )
    transitions: list[float] = []
    for previous, current in pairwise(daily_percentiles):
        common = sorted(set(previous) & set(current))
        if len(common) >= minimum_common:
            transitions.append(
                sum(abs(current[item] - previous[item]) for item in common) / len(common)
            )
    return (
        (float(median(transitions)) if len(transitions) >= minimum_transitions else None),
        len(transitions),
    )


def pair_correlation_evidence(
    *,
    left_feature_key: str,
    right_feature_key: str,
    left_feature_id: str,
    right_feature_id: str,
    left_envelopes: Sequence[CoreProcessedFeatureEnvelope],
    right_envelopes: Sequence[CoreProcessedFeatureEnvelope],
    minimum_pairs: int = 5,
    minimum_dates: int = 60,
) -> CorePairCorrelationEvidence:
    left_by_date = {item.decision_date: item for item in left_envelopes}
    right_by_date = {item.decision_date: item for item in right_envelopes}
    if tuple(sorted(left_by_date)) != tuple(sorted(right_by_date)):
        raise ValueError("correlation panels must use the same daily calendar")
    correlations: list[float] = []
    for decision_date in sorted(left_by_date):
        correlation = spearman_by_key(
            observed_feature_map(left_by_date[decision_date], left_feature_id),
            observed_feature_map(right_by_date[decision_date], right_feature_id),
            minimum_pairs=minimum_pairs,
        )
        if correlation is not None:
            correlations.append(correlation)
    if len(correlations) < minimum_dates:
        return CorePairCorrelationEvidence(
            left_feature_key=min(left_feature_key, right_feature_key),
            right_feature_key=max(left_feature_key, right_feature_key),
            valid_date_count=len(correlations),
            status=CoreCorrelationStatus.CORRELATION_EVIDENCE_INSUFFICIENT,
        )
    aggregated = float(median(correlations))
    return CorePairCorrelationEvidence(
        left_feature_key=min(left_feature_key, right_feature_key),
        right_feature_key=max(left_feature_key, right_feature_key),
        valid_date_count=len(correlations),
        median_daily_spearman=aggregated,
        distance=1.0 - abs(aggregated),
        status=CoreCorrelationStatus.AVAILABLE,
    )


def correlation_distance_map(
    evidence: Sequence[CorePairCorrelationEvidence],
) -> Mapping[frozenset[str], float | None]:
    return {
        frozenset((item.left_feature_key, item.right_feature_key)): item.distance
        for item in evidence
    }


__all__ = [
    "correlation_distance_map",
    "feature_turnover",
    "observed_feature_map",
    "pair_correlation_evidence",
]
