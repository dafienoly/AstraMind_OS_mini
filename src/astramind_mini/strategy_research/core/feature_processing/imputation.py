"""State-aware daily industry/U0 median imputation."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from statistics import median

from ..feature_values import (
    CoreFeatureValue,
    CoreImputationSource,
    FeatureAvailabilityState,
)
from .control import CoreProcessingControlRow
from .models import CoreProcessingSpec


def state_aware_imputation_values(
    raw_rows: Sequence[CoreFeatureValue],
    *,
    standardized_by_instrument: Mapping[str, float],
    controls: Mapping[str, CoreProcessingControlRow],
    spec: CoreProcessingSpec,
) -> dict[str, tuple[float, CoreImputationSource]]:
    """Fill non-observed rows while preserving their tri-state indicators."""
    if not standardized_by_instrument:
        return {}
    u0_median = float(median(standardized_by_instrument.values()))
    industry_values: dict[str, list[float]] = defaultdict(list)
    for instrument, value in standardized_by_instrument.items():
        industry = controls[instrument].sw_l1
        if industry is not None:
            industry_values[str(industry)].append(value)
    industry_medians = {
        industry: float(median(values))
        for industry, values in industry_values.items()
        if len(values) >= spec.industry_imputation_minimum_observed
    }
    result: dict[str, tuple[float, CoreImputationSource]] = {}
    for item in raw_rows:
        if item.availability_state == FeatureAvailabilityState.OBSERVED:
            continue
        industry = controls[item.instrument_id].sw_l1
        if (
            item.availability_state == FeatureAvailabilityState.MISSING
            and industry is not None
            and str(industry) in industry_medians
        ):
            result[item.instrument_id] = (
                industry_medians[str(industry)],
                CoreImputationSource.SW_L1_MEDIAN,
            )
        else:
            result[item.instrument_id] = (
                u0_median,
                CoreImputationSource.U0_MEDIAN,
            )
    return result


__all__ = ["state_aware_imputation_values"]
