"""Formula-level availability result."""

from __future__ import annotations

import math
from dataclasses import dataclass

from ..feature_values import FeatureAvailabilityState
from .reasons import F0Reason


@dataclass(frozen=True)
class FormulaResult:
    value: float | None
    state: FeatureAvailabilityState
    reason: F0Reason | None


def observed(value: float) -> FormulaResult:
    if not math.isfinite(value):
        return missing(F0Reason.NON_FINITE_RESULT)
    return FormulaResult(value, FeatureAvailabilityState.OBSERVED, None)


def missing(reason: F0Reason) -> FormulaResult:
    return FormulaResult(None, FeatureAvailabilityState.MISSING, reason)


def not_applicable(
    reason: F0Reason = F0Reason.FINANCIAL_NOT_APPLICABLE,
) -> FormulaResult:
    return FormulaResult(
        None,
        FeatureAvailabilityState.NOT_APPLICABLE,
        reason,
    )


__all__ = ["FormulaResult", "missing", "not_applicable", "observed"]
