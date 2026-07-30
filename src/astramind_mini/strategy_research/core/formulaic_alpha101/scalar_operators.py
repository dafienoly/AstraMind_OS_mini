"""Pure scalar/window semantics for alpha101-operator-semantics-v1."""

from __future__ import annotations

import math
from collections.abc import Sequence

from .reasons import Alpha101Failure, Alpha101Reason


def finite(value: float) -> float:
    if not math.isfinite(value):
        raise Alpha101Failure(Alpha101Reason.NONFINITE)
    return value


def divide(numerator: float, denominator: float) -> float:
    finite(numerator)
    finite(denominator)
    if denominator == 0:
        raise Alpha101Failure(Alpha101Reason.ZERO_DENOMINATOR)
    return finite(numerator / denominator)


def logarithm(value: float) -> float:
    if value <= 0:
        raise Alpha101Failure(Alpha101Reason.LOG_DOMAIN)
    return finite(math.log(value))


def power(base: float, exponent: float) -> float:
    if (base == 0 and exponent <= 0) or (base < 0 and not exponent.is_integer()):
        raise Alpha101Failure(Alpha101Reason.POWER_DOMAIN)
    try:
        return finite(base**exponent)
    except OverflowError as error:
        raise Alpha101Failure(Alpha101Reason.NONFINITE) from error


def signed_power(base: float, exponent: float) -> float:
    if base == 0 and exponent <= 0:
        raise Alpha101Failure(Alpha101Reason.POWER_DOMAIN)
    try:
        return finite(math.copysign(abs(base) ** exponent, base) if base else 0.0)
    except OverflowError as error:
        raise Alpha101Failure(Alpha101Reason.NONFINITE) from error


def complete(values: Sequence[float | None], window: int) -> tuple[float, ...]:
    if window < 1 or len(values) < window:
        raise Alpha101Failure(Alpha101Reason.WINDOW_INCOMPLETE)
    selected = values[-window:]
    if any(value is None for value in selected):
        raise Alpha101Failure(Alpha101Reason.INPUT_MISSING)
    return tuple(finite(value) for value in selected if value is not None)


def average_rank(values: Sequence[float]) -> tuple[float, ...]:
    if len(values) < 2:
        raise Alpha101Failure(Alpha101Reason.CROSS_SECTION_TOO_SMALL)
    order = sorted(range(len(values)), key=values.__getitem__)
    result = [0.0] * len(values)
    start = 0
    while start < len(order):
        end = start + 1
        while end < len(order) and values[order[end]] == values[order[start]]:
            end += 1
        average_position = (start + end - 1) / 2
        normalized = average_position / (len(values) - 1)
        for position in order[start:end]:
            result[position] = normalized
        start = end
    return tuple(result)


def scale(values: Sequence[float], target: float = 1.0) -> tuple[float, ...]:
    norm = finite(sum(abs(value) for value in values))
    if norm == 0:
        raise Alpha101Failure(Alpha101Reason.SCALE_ZERO_NORM)
    return tuple(finite(value * target / norm) for value in values)


def stddev(values: Sequence[float]) -> float:
    try:
        mean = finite(sum(values) / len(values))
        squared_deviations = finite(sum((value - mean) ** 2 for value in values))
        return finite(math.sqrt(squared_deviations / len(values)))
    except OverflowError as error:
        raise Alpha101Failure(Alpha101Reason.NONFINITE) from error


def covariance(left: Sequence[float], right: Sequence[float]) -> float:
    try:
        left_mean = finite(sum(left) / len(left))
        right_mean = finite(sum(right) / len(right))
        products = finite(
            sum((x - left_mean) * (y - right_mean) for x, y in zip(left, right, strict=True))
        )
        return finite(products / len(left))
    except OverflowError as error:
        raise Alpha101Failure(Alpha101Reason.NONFINITE) from error


def correlation(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) == len(right) == 2:
        left_delta = finite(left[1] - left[0])
        right_delta = finite(right[1] - right[0])
        if left_delta == 0 or right_delta == 0:
            raise Alpha101Failure(Alpha101Reason.ZERO_VARIANCE)
        return 1.0 if (left_delta > 0) == (right_delta > 0) else -1.0
    left_std = stddev(left)
    right_std = stddev(right)
    if left_std == 0 or right_std == 0:
        raise Alpha101Failure(Alpha101Reason.ZERO_VARIANCE)
    return divide(covariance(left, right), left_std * right_std)


def decay_linear(values: Sequence[float]) -> float:
    weights = range(1, len(values) + 1)
    weighted = sum(value * weight for value, weight in zip(values, weights, strict=True))
    return finite(weighted / sum(weights))


def time_series_rank(values: Sequence[float]) -> float:
    return average_rank(values)[-1]


def first_extreme_position(values: Sequence[float], *, maximum: bool) -> float:
    extreme = max(values) if maximum else min(values)
    return float(values.index(extreme))


__all__ = [
    "average_rank",
    "complete",
    "correlation",
    "covariance",
    "decay_linear",
    "divide",
    "finite",
    "first_extreme_position",
    "logarithm",
    "power",
    "scale",
    "signed_power",
    "stddev",
    "time_series_rank",
]
