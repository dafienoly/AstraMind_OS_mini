"""Internal three-state cells for Alpha101 expression evaluation."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from ..feature_values import FeatureAvailabilityState
from .reasons import Alpha101Reason

_NOT_APPLICABLE = {
    Alpha101Reason.SW_L1_NOT_POINT_IN_TIME,
    Alpha101Reason.SW_L2_NOT_POINT_IN_TIME,
    Alpha101Reason.SW_L3_UNAVAILABLE,
}


@dataclass(frozen=True)
class Alpha101Cell:
    value: float | None
    reason: Alpha101Reason | None = None

    def __post_init__(self) -> None:
        if self.reason is None:
            if self.value is None or not isfinite(self.value):
                raise ValueError("observed Alpha101 cells require one finite value")
            return
        if not isinstance(self.reason, Alpha101Reason) or self.value is not None:
            raise ValueError("unavailable Alpha101 cells require one reason and no value")

    @property
    def state(self) -> FeatureAvailabilityState:
        if self.reason is None:
            return FeatureAvailabilityState.OBSERVED
        if self.reason in _NOT_APPLICABLE:
            return FeatureAvailabilityState.NOT_APPLICABLE
        return FeatureAvailabilityState.MISSING


OBSERVED_ZERO = Alpha101Cell(0.0)
Matrix = tuple[tuple[Alpha101Cell, ...], ...]


def missing(reason: Alpha101Reason) -> Alpha101Cell:
    return Alpha101Cell(None, reason)


__all__ = ["OBSERVED_ZERO", "Alpha101Cell", "Matrix", "missing"]
