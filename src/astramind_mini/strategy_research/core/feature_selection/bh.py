"""Deterministic Benjamini-Hochberg family correction."""

from __future__ import annotations

from collections.abc import Mapping


def benjamini_hochberg(
    p_values: Mapping[str, float | None],
    *,
    fdr: float = 0.10,
) -> dict[str, tuple[int, float, bool]]:
    """Return rank, threshold and pass flag; absent p-values are outside m."""
    eligible = sorted(
        (
            (feature_key, float(p_value))
            for feature_key, p_value in p_values.items()
            if p_value is not None
        ),
        key=lambda item: (item[1], item[0]),
    )
    if not 0.0 < fdr < 1.0:
        raise ValueError("BH FDR must be between zero and one")
    if any(not 0.0 <= value <= 1.0 for _, value in eligible):
        raise ValueError("BH p-values must be finite probabilities")
    maximum_passing_rank = 0
    for rank, (_, p_value) in enumerate(eligible, start=1):
        if p_value <= rank / len(eligible) * fdr:
            maximum_passing_rank = rank
    return {
        feature_key: (
            rank,
            rank / len(eligible) * fdr,
            rank <= maximum_passing_rank,
        )
        for rank, (feature_key, _) in enumerate(eligible, start=1)
    }


__all__ = ["benjamini_hochberg"]
