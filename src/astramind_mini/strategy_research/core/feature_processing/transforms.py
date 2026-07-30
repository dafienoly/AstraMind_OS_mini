"""Pure robust cross-sectional transformation primitives."""

from __future__ import annotations

import math
from collections.abc import Sequence
from statistics import median

from .models import CoreCrossSectionStatus, CoreProcessingSpec


def robust_cross_section(
    values: Sequence[float],
    *,
    spec: CoreProcessingSpec,
) -> tuple[
    CoreCrossSectionStatus,
    float | None,
    float | None,
    float | None,
    float | None,
    tuple[float, ...],
    tuple[float, ...],
]:
    """Apply fixed MAD winsorization and z-scoring to finite observed values."""
    spec = CoreProcessingSpec.model_validate(spec.model_dump())
    if any(not math.isfinite(item) for item in values):
        raise ValueError("non-finite observed input is rejected before processing")
    if not values:
        return (
            CoreCrossSectionStatus.NO_OBSERVED,
            None,
            None,
            None,
            None,
            (),
            (),
        )
    center = float(median(values))
    scale = spec.mad_consistency_constant * float(median(abs(item - center) for item in values))
    lower = center - spec.winsor_mad_multiple * scale
    upper = center + spec.winsor_mad_multiple * scale
    if scale == 0.0:
        return (
            CoreCrossSectionStatus.ZERO_SCALE,
            center,
            0.0,
            center,
            center,
            tuple(float(item) for item in values),
            tuple(0.0 for _ in values),
        )
    winsorized = tuple(min(max(float(item), lower), upper) for item in values)
    standardized = tuple((item - center) / scale for item in winsorized)
    return (
        CoreCrossSectionStatus.READY,
        center,
        scale,
        lower,
        upper,
        winsorized,
        standardized,
    )


__all__ = ["robust_cross_section"]
