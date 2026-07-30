"""Canonical quality ordering for a correlation-cluster representative."""

from __future__ import annotations

from typing import Protocol


class RepresentativeEvidence(Protocol):
    feature_key: str
    direction_consistent: bool
    complexity: int
    coverage_mean: float | None
    turnover: float | None
    stability: float | None


def representative_sort_key(evidence: RepresentativeEvidence) -> tuple[object, ...]:
    return (
        not evidence.direction_consistent,
        evidence.complexity,
        evidence.coverage_mean is None,
        -(evidence.coverage_mean or 0.0),
        evidence.turnover is None,
        evidence.turnover or 0.0,
        evidence.stability is None,
        -(evidence.stability or 0.0),
        evidence.feature_key,
    )


__all__ = ["representative_sort_key"]
