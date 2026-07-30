"""Deterministic cross-sectional average-rank percentiles for core labels."""

from __future__ import annotations

from collections.abc import Sequence


def average_rank_percentiles(values: Sequence[tuple[str, float]]) -> dict[str, float]:
    """Return ascending average-rank percentiles with stable identifier ties."""
    ordered = sorted(values, key=lambda item: (item[1], item[0]))
    if len(ordered) < 2:
        return {}
    result: dict[str, float] = {}
    index = 0
    while index < len(ordered):
        end = index + 1
        while end < len(ordered) and ordered[end][1] == ordered[index][1]:
            end += 1
        average_rank = ((index + 1) + end) / 2.0
        percentile = (average_rank - 1.0) / (len(ordered) - 1)
        for instrument_id, _ in ordered[index:end]:
            result[instrument_id] = percentile
        index = end
    return result


__all__ = ["average_rank_percentiles"]
