"""Pure scoring for an industry-internal research queue."""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from math import exp, isfinite

from ..contracts.ranking import IndustryResearchRow, ResearchLabel

SCORING_VERSION = "industry-research-priority-v1.0.0"


@dataclass(frozen=True)
class RankingFeature:
    instrument_id: str
    instrument_name: str
    industry_code: str
    membership_effective_as_of: date
    return_1d: float | None
    return_5d: float | None
    return_20d: float | None
    return_60d: float | None
    position_120d: float | None
    turnover_rate: float | None
    amount_share: float | None
    volatility_20d: float | None
    downside_volatility_20d: float | None
    drawdown_60d: float | None
    price_earnings_ttm: float | None
    price_book: float | None
    dividend_yield_ttm: float | None
    holder_change_rate: float | None
    lhb_attention: float | None
    below_ma_count: int | None


def rank_industry(
    features: Sequence[RankingFeature],
    *,
    market_features: Sequence[RankingFeature],
    evidence_cutoff: date,
    lifecycle_stage: str,
) -> tuple[IndustryResearchRow, ...]:
    population = features if len(features) >= 5 else market_features
    distributions = _distributions(population)
    rows = [
        _score(
            item, distributions, evidence_cutoff=evidence_cutoff, lifecycle_stage=lifecycle_stage
        )
        for item in features
    ]
    return tuple(sorted(rows, key=_sort_key))


def _score(
    item: RankingFeature,
    distributions: Mapping[str, Sequence[float]],
    *,
    evidence_cutoff: date,
    lifecycle_stage: str,
) -> IndustryResearchRow:
    label: ResearchLabel
    components = {
        "event": _weighted(
            (
                (_rank(distributions, "return_1d", item.return_1d), 0.15),
                (_rank(distributions, "return_5d", item.return_5d), 0.30),
                (_rank(distributions, "turnover_rate", item.turnover_rate), 0.20),
                (_rank(distributions, "amount_share", item.amount_share), 0.20),
                (_rank(distributions, "lhb_attention", item.lhb_attention), 0.15),
            )
        ),
        "technical": _weighted(
            (
                (_rank(distributions, "return_20d", item.return_20d), 0.30),
                (_rank(distributions, "return_60d", item.return_60d), 0.25),
                (_rank(distributions, "position_120d", item.position_120d), 0.25),
                (_inverse_rank(distributions, "volatility_20d", item.volatility_20d), 0.20),
            )
        ),
        "fundamental": _weighted(
            (
                (
                    _positive_inverse(distributions, "price_earnings_ttm", item.price_earnings_ttm),
                    0.35,
                ),
                (_positive_inverse(distributions, "price_book", item.price_book), 0.25),
                (_rank(distributions, "dividend_yield_ttm", item.dividend_yield_ttm), 0.20),
                (_inverse_rank(distributions, "holder_change_rate", item.holder_change_rate), 0.20),
            )
        ),
        "safety": _weighted(
            (
                (_inverse_rank(distributions, "volatility_20d", item.volatility_20d), 0.35),
                (
                    _inverse_rank(
                        distributions,
                        "downside_volatility_20d",
                        item.downside_volatility_20d,
                    ),
                    0.30,
                ),
                (_rank(distributions, "drawdown_60d", item.drawdown_60d), 0.35),
            )
        ),
    }
    coverage = sum(
        weight * (components[name][1] / component_weight)
        for name, weight, component_weight in (
            ("event", 0.25, 1.0),
            ("technical", 0.35, 1.0),
            ("fundamental", 0.20, 1.0),
            ("safety", 0.20, 1.0),
        )
    )
    reversal = _reversal(item)
    values = {name: score for name, (score, _) in components.items()}
    gaps = tuple(
        f"{name}_coverage_below_full" for name, (_, found) in components.items() if found < 0.999
    )
    if coverage < 0.60:
        overall = None
        label = "数据不足"
    else:
        overall = (
            0.25 * (values["event"] or 50.0)
            + 0.35 * (values["technical"] or 50.0)
            + 0.20 * (values["fundamental"] or 50.0)
            + 0.20 * (values["safety"] or 50.0)
            + _lifecycle_adjustment(lifecycle_stage)
        )
        if reversal >= 75:
            overall = min(overall, 35.0)
        elif reversal >= 55:
            overall = min(overall, 55.0)
        overall = round(max(0.0, min(100.0, overall)), 2)
        risk = None if values["safety"] is None else round(100.0 - values["safety"], 2)
        if overall >= 70 and (risk or 100) < 60 and reversal < 55:
            label = "优先研究"
        elif overall >= 60 and (risk or 100) < 70 and reversal < 75:
            label = "积极关注"
        else:
            label = "中性观察"
    return IndustryResearchRow(
        instrument_id=item.instrument_id,
        instrument_name=item.instrument_name,
        membership_effective_as_of=item.membership_effective_as_of,
        overall_priority=overall,
        event_sentiment_score=_rounded(values["event"]),
        technical_volume_score=_rounded(values["technical"]),
        fundamental_score=_rounded(values["fundamental"]),
        risk_score=_rounded(None if values["safety"] is None else 100.0 - values["safety"]),
        reversal_repair_score=round(reversal, 2),
        coverage=round(coverage, 4),
        research_label=label,
        evidence_cutoff=evidence_cutoff,
        known_gaps=gaps,
    )


def _distributions(items: Sequence[RankingFeature]) -> dict[str, list[float]]:
    result: dict[str, list[float]] = {}
    for name in RankingFeature.__dataclass_fields__:
        values = [_number(getattr(item, name)) for item in items]
        result[name] = sorted(value for value in values if value is not None)
    return result


def _weighted(items: Sequence[tuple[float | None, float]]) -> tuple[float | None, float]:
    found = [(value, weight) for value, weight in items if value is not None]
    coverage = sum(weight for _, weight in found)
    if not found:
        return None, 0.0
    return 100.0 * sum(value * weight for value, weight in found) / coverage, coverage


def _rank(values: Mapping[str, Sequence[float]], name: str, value: float | None) -> float | None:
    number = _number(value)
    ordered = values.get(name, ())
    if number is None or not ordered:
        return None
    left, right = bisect_left(ordered, number), bisect_right(ordered, number)
    return (left + (right - left + 1) / 2) / len(ordered)


def _inverse_rank(
    values: Mapping[str, Sequence[float]], name: str, value: float | None
) -> float | None:
    ranked = _rank(values, name, value)
    return None if ranked is None else 1.0 - ranked


def _positive_inverse(
    values: Mapping[str, Sequence[float]], name: str, value: float | None
) -> float | None:
    return None if value is None or value <= 0 else _inverse_rank(values, name, value)


def _reversal(item: RankingFeature) -> float:
    r1 = item.return_1d or 0.0
    r5 = item.return_5d or 0.0
    drawdown = item.drawdown_60d or 0.0
    below = (item.below_ma_count or 0) / 3.0
    return 100.0 * (
        0.30 * _sigmoid((-r1 - 0.05) / 0.015)
        + 0.30 * _sigmoid((-r5 - 0.10) / 0.03)
        + 0.25 * _sigmoid((-drawdown - 0.12) / 0.03)
        + 0.15 * below
    )


def _lifecycle_adjustment(stage: str) -> float:
    return {
        "强势扩散": 5.0,
        "低位修复": 3.0,
        "退潮观察": -4.0,
        "明显退潮": -8.0,
        "极端低位": -3.0,
    }.get(stage, 0.0)


def _sigmoid(value: float) -> float:
    return 1.0 / (1.0 + exp(-value))


def _number(value: object) -> float | None:
    return float(value) if isinstance(value, (int, float)) and isfinite(float(value)) else None


def _rounded(value: float | None) -> float | None:
    return None if value is None else round(value, 2)


def _sort_key(item: IndustryResearchRow) -> tuple[bool, float, str]:
    return item.overall_priority is None, -(item.overall_priority or 0.0), item.instrument_id


__all__ = ["SCORING_VERSION", "RankingFeature", "rank_industry"]
