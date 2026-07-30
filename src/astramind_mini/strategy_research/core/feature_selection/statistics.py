"""Small deterministic statistical primitives for fold-internal selection."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from statistics import median


def average_ranks(values: Sequence[float]) -> tuple[float, ...]:
    order = sorted(range(len(values)), key=lambda index: (values[index], index))
    ranks = [0.0] * len(values)
    position = 0
    while position < len(order):
        end = position + 1
        while end < len(order) and values[order[end]] == values[order[position]]:
            end += 1
        average = ((position + 1) + end) / 2.0
        for index in order[position:end]:
            ranks[index] = average
        position = end
    return tuple(ranks)


def spearman(values_x: Sequence[float], values_y: Sequence[float]) -> float | None:
    if len(values_x) != len(values_y) or len(values_x) < 2:
        return None
    ranks_x = average_ranks(values_x)
    ranks_y = average_ranks(values_y)
    mean_x = sum(ranks_x) / len(ranks_x)
    mean_y = sum(ranks_y) / len(ranks_y)
    covariance = sum(
        (left - mean_x) * (right - mean_y) for left, right in zip(ranks_x, ranks_y, strict=True)
    )
    variance_x = sum((item - mean_x) ** 2 for item in ranks_x)
    variance_y = sum((item - mean_y) ** 2 for item in ranks_y)
    denominator = math.sqrt(variance_x * variance_y)
    return covariance / denominator if denominator > 0.0 else None


def spearman_by_key(
    values_x: Mapping[str, float],
    values_y: Mapping[str, float],
    *,
    minimum_pairs: int,
) -> float | None:
    common = sorted(set(values_x) & set(values_y))
    if len(common) < minimum_pairs:
        return None
    return spearman(
        tuple(values_x[key] for key in common),
        tuple(values_y[key] for key in common),
    )


def median_absolute_deviation(values: Sequence[float]) -> float | None:
    if not values:
        return None
    center = float(median(values))
    return float(median(abs(item - center) for item in values))


def finite_mean(values: Sequence[float]) -> float | None:
    if not values or any(not math.isfinite(item) for item in values):
        return None
    return sum(values) / len(values)


__all__ = [
    "average_ranks",
    "finite_mean",
    "median_absolute_deviation",
    "spearman",
    "spearman_by_key",
]
