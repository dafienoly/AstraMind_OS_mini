"""Parallel industry/size neutralization diagnostics."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import cast

import numpy as np

from .control import CoreProcessingControlRow
from .models import CoreNeutralizationStatus, CoreProcessingSpec


def neutralization_residuals(
    observed: Sequence[tuple[str, float]],
    controls: Mapping[str, CoreProcessingControlRow],
    *,
    spec: CoreProcessingSpec,
) -> tuple[CoreNeutralizationStatus, int, int, dict[str, float]]:
    """Fit the frozen diagnostic OLS without changing the main feature."""
    if any(
        instrument not in controls
        or controls[instrument].sw_l1 is None
        or controls[instrument].float_market_cap is None
        for instrument, _ in observed
    ):
        return CoreNeutralizationStatus.CONTROLS_MISSING, len(observed), 0, {}
    industries = sorted({str(controls[instrument].sw_l1) for instrument, _ in observed})
    parameter_count = 2 + max(0, len(industries) - 1)
    if len(observed) < spec.neutralization_minimum_n_per_parameter * parameter_count:
        return (
            CoreNeutralizationStatus.INSUFFICIENT_SAMPLE,
            len(observed),
            parameter_count,
            {},
        )
    baseline = industries[0]
    matrix_rows: list[list[float]] = []
    for instrument, _ in observed:
        market_cap = cast(float, controls[instrument].float_market_cap)
        row = [1.0, math.log(market_cap)]
        row.extend(
            1.0 if controls[instrument].sw_l1 == industry else 0.0
            for industry in industries
            if industry != baseline
        )
        matrix_rows.append(row)
    matrix = np.asarray(matrix_rows, dtype=np.float64)
    if int(np.linalg.matrix_rank(matrix)) != parameter_count:
        return (
            CoreNeutralizationStatus.RANK_DEFICIENT,
            len(observed),
            parameter_count,
            {},
        )
    target = np.asarray([value for _, value in observed], dtype=np.float64)
    coefficients, _, _, _ = np.linalg.lstsq(matrix, target, rcond=None)
    residuals = target - matrix @ coefficients
    return (
        CoreNeutralizationStatus.AVAILABLE,
        len(observed),
        parameter_count,
        {
            instrument: float(residual)
            for (instrument, _), residual in zip(observed, residuals, strict=True)
        },
    )


__all__ = ["neutralization_residuals"]
