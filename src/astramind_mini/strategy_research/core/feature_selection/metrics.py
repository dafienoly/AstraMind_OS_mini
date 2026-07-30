"""Panel metrics used by both within-package and joint selection."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from statistics import median

from ..feature_processing import CoreProcessedFeatureEnvelope
from .models import CoreCorrelationStatus, CorePairCorrelationEvidence
from .observations import observed_feature_map
from .statistics import spearman_by_key


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
    "observed_feature_map",
    "pair_correlation_evidence",
]
