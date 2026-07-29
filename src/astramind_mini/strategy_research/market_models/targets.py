"""Pure target and ETF research-weight rules for market model v2."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

LifecycleStage = Literal[
    "obvious_decline",
    "low_position_repair",
    "strong_expansion",
    "extreme_low",
    "decline_watch",
    "unclear",
]


def simple_return(start: float, end: float) -> float:
    if start <= 0 or end < 0:
        raise ValueError("return prices must be non-negative and start must be positive")
    return end / start - 1.0


def excess_return(
    *,
    asset_start: float,
    asset_end: float,
    benchmark_start: float,
    benchmark_end: float,
) -> float:
    return simple_return(asset_start, asset_end) - simple_return(
        benchmark_start,
        benchmark_end,
    )


def lifecycle_stage_label(
    *,
    future_20d_excess_percentile: float,
    future_20d_max_drawdown: float,
    current_low_participation_percentile: float,
    current_strong_participation_percentile: float,
) -> LifecycleStage:
    values = (
        future_20d_excess_percentile,
        current_low_participation_percentile,
        current_strong_participation_percentile,
    )
    if any(value < 0 or value > 1 for value in values):
        raise ValueError("lifecycle percentiles must be within [0, 1]")
    if future_20d_max_drawdown > 0:
        raise ValueError("maximum drawdown must not be positive")
    if future_20d_excess_percentile <= 0.20 and future_20d_max_drawdown <= -0.08:
        return "obvious_decline"
    if current_low_participation_percentile >= 0.70 and future_20d_excess_percentile >= 0.60:
        return "low_position_repair"
    if future_20d_excess_percentile >= 0.70:
        return "strong_expansion"
    if (
        current_low_participation_percentile >= 0.85
        and current_strong_participation_percentile <= 0.15
    ):
        return "extreme_low"
    if future_20d_excess_percentile <= 0.35:
        return "decline_watch"
    return "unclear"


def industry_research_target(
    *,
    future_20d_within_industry_rank: float,
    future_60d_within_industry_rank: float,
) -> float:
    _validate_rank(future_20d_within_industry_rank)
    _validate_rank(future_60d_within_industry_rank)
    return 0.7 * future_20d_within_industry_rank + 0.3 * future_60d_within_industry_rank


def shrunk_industry_rank(
    *,
    industry_rank: float,
    market_rank: float,
    industry_sample_size: int,
    shrinkage: int = 10,
) -> float:
    _validate_rank(industry_rank)
    _validate_rank(market_rank)
    if industry_sample_size < 0 or shrinkage <= 0:
        raise ValueError("sample size must be non-negative and shrinkage must be positive")
    industry_weight = industry_sample_size / (industry_sample_size + shrinkage)
    return industry_weight * industry_rank + (1.0 - industry_weight) * market_rank


def etf_net_excess_target(
    *,
    etf_start: float,
    etf_end: float,
    official_benchmark_start: float,
    official_benchmark_end: float,
    round_trip_cost_rate: float,
) -> float:
    if round_trip_cost_rate < 0:
        raise ValueError("round-trip cost cannot be negative")
    return (
        excess_return(
            asset_start=etf_start,
            asset_end=etf_end,
            benchmark_start=official_benchmark_start,
            benchmark_end=official_benchmark_end,
        )
        - round_trip_cost_rate
    )


@dataclass(frozen=True)
class EtfWeightCandidate:
    instrument_id: str
    predicted_net_excess: float
    annualized_volatility: float


@dataclass(frozen=True)
class EtfResearchWeights:
    weights: tuple[tuple[str, float], ...]
    cash_weight: float
    rejected_correlated: tuple[str, ...]


def etf_inverse_volatility_weights(
    candidates: Sequence[EtfWeightCandidate],
    *,
    correlations: Mapping[tuple[str, str], float],
    total_exposure: float = 0.60,
    single_cap: float = 0.35,
    correlation_cap: float = 0.85,
) -> EtfResearchWeights:
    if not 0 < total_exposure <= 1 or not 0 < single_cap <= total_exposure:
        raise ValueError("ETF exposure limits are invalid")
    ordered = sorted(
        (
            candidate
            for candidate in candidates
            if candidate.predicted_net_excess > 0
            and math.isfinite(candidate.annualized_volatility)
            and candidate.annualized_volatility > 0
        ),
        key=lambda item: (-item.predicted_net_excess, item.instrument_id),
    )
    selected: list[EtfWeightCandidate] = []
    rejected: list[str] = []
    for candidate in ordered:
        if any(
            _correlation(candidate.instrument_id, existing.instrument_id, correlations)
            > correlation_cap
            for existing in selected
        ):
            rejected.append(candidate.instrument_id)
            continue
        selected.append(candidate)
        if len(selected) == 2:
            break
    weights = _capped_inverse_volatility(
        selected,
        total_exposure=total_exposure,
        single_cap=single_cap,
    )
    invested = sum(weight for _, weight in weights)
    return EtfResearchWeights(
        weights=weights,
        cash_weight=1.0 - invested,
        rejected_correlated=tuple(rejected),
    )


def _capped_inverse_volatility(
    candidates: Sequence[EtfWeightCandidate],
    *,
    total_exposure: float,
    single_cap: float,
) -> tuple[tuple[str, float], ...]:
    if not candidates:
        return ()
    inverse = [1.0 / candidate.annualized_volatility for candidate in candidates]
    weights = [total_exposure * item / sum(inverse) for item in inverse]
    weights = [min(weight, single_cap) for weight in weights]
    remaining = total_exposure - sum(weights)
    while remaining > 1e-12:
        open_indexes = [index for index, value in enumerate(weights) if value < single_cap]
        if not open_indexes:
            break
        increment = remaining / len(open_indexes)
        before = sum(weights)
        for index in open_indexes:
            weights[index] = min(single_cap, weights[index] + increment)
        remaining -= sum(weights) - before
    return tuple(
        (candidate.instrument_id, weight)
        for candidate, weight in zip(candidates, weights, strict=True)
    )


def _correlation(
    left: str,
    right: str,
    correlations: Mapping[tuple[str, str], float],
) -> float:
    value = correlations.get((left, right), correlations.get((right, left)))
    if value is None or not math.isfinite(value):
        raise ValueError(f"missing ETF correlation for {left}/{right}")
    return value


def _validate_rank(value: float) -> None:
    if not math.isfinite(value) or not 0 <= value <= 1:
        raise ValueError("rank must be finite and within [0, 1]")


__all__ = [
    "EtfResearchWeights",
    "EtfWeightCandidate",
    "LifecycleStage",
    "etf_inverse_volatility_weights",
    "etf_net_excess_target",
    "excess_return",
    "industry_research_target",
    "lifecycle_stage_label",
    "shrunk_industry_rank",
    "simple_return",
]
