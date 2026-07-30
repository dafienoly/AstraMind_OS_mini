"""Standalone handwritten Alpha101 anchors with no production imports."""

from __future__ import annotations

import hashlib
import math
from collections.abc import Sequence
from pathlib import Path

GENERATOR_NAME = "standalone-handwritten-alpha101-equations"
GENERATOR_VERSION = "2.0.0"


def generator_source_hash() -> str:
    return "sha256:" + hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def independent_operator_expected() -> dict[str, float | list[float]]:
    values = (10.0, 20.0, 20.0, 40.0)
    return {
        "rank_ties": list(_rank(values)),
        "ts_rank": _rank((4.0, 2.0, 2.0))[-1],
        "stddev": _population_std((1.0, 2.0, 3.0)),
        "covariance": _population_covariance(
            (1.0, 2.0, 3.0),
            (2.0, 4.0, 8.0),
        ),
        "correlation": _correlation(
            (1.0, 2.0, 3.0),
            (2.0, 4.0, 6.0),
        ),
        "decay_linear": sum(
            value * weight for value, weight in zip((10.0, 20.0, 40.0), (1, 2, 3), strict=True)
        )
        / 6,
        "argmax": float((3.0, 7.0, 7.0).index(7.0)),
        "argmin": float((2.0, 1.0, 1.0).index(1.0)),
        "signedpower_negative_square": -4.0,
    }


def _rank(values: Sequence[float]) -> tuple[float, ...]:
    order = sorted(range(len(values)), key=values.__getitem__)
    result = [0.0] * len(values)
    start = 0
    while start < len(order):
        end = start + 1
        while end < len(order) and values[order[end]] == values[order[start]]:
            end += 1
        average_zero_based_position = (start + end - 1) / 2
        for index in order[start:end]:
            result[index] = average_zero_based_position / (len(values) - 1)
        start = end
    return tuple(result)


def _population_std(values: Sequence[float]) -> float:
    mean = sum(values) / len(values)
    return math.sqrt(sum((value - mean) ** 2 for value in values) / len(values))


def _population_covariance(left: Sequence[float], right: Sequence[float]) -> float:
    left_mean = sum(left) / len(left)
    right_mean = sum(right) / len(right)
    return sum((x - left_mean) * (y - right_mean) for x, y in zip(left, right, strict=True)) / len(
        left
    )


def _correlation(left: Sequence[float], right: Sequence[float]) -> float:
    return _population_covariance(left, right) / (_population_std(left) * _population_std(right))


__all__ = [
    "GENERATOR_NAME",
    "GENERATOR_VERSION",
    "generator_source_hash",
    "independent_operator_expected",
]
