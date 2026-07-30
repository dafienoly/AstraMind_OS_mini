"""Canonical observed-value extraction from processed feature envelopes."""

from __future__ import annotations

from ..feature_processing import CoreProcessedFeatureEnvelope
from ..feature_values import FeatureAvailabilityState


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


__all__ = ["observed_feature_map"]
