"""Point-in-time industry aggregation and lifecycle stage rules."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from statistics import median
from typing import Protocol

from ..contracts.lifecycle import (
    IndustryLifecyclePoint,
    LifecycleConfidence,
    LifecycleStage,
    LifecycleTrajectoryPoint,
)


class StructureState(Protocol):
    @property
    def strong(self) -> bool: ...

    @property
    def low(self) -> bool: ...


@dataclass(frozen=True)
class MembershipInterval:
    instrument_id: str
    industry_code: str
    effective_from: date
    effective_to: date | None


@dataclass(frozen=True)
class IndustryIdentity:
    industry_code: str
    industry_name: str


def lifecycle_stage(
    *,
    strong: float,
    low: float,
    delta_strong: float,
    delta_low: float,
    peak_strong: float,
) -> LifecycleStage:
    drawdown = peak_strong - strong
    if peak_strong >= 25 and drawdown >= 15 and delta_strong <= -5 and delta_low >= 5:
        return "明显退潮"
    if peak_strong >= 18 and drawdown >= 7 and delta_strong <= -2 and delta_low >= 2:
        return "退潮观察"
    if strong >= 20 and low <= 35 and delta_strong >= 1 and delta_low <= 0:
        return "强势扩散"
    if low >= 40 and delta_low <= -5 and delta_strong >= 1:
        return "低位修复"
    if low >= 55 and strong <= 8:
        return "极端低位"
    return "方向未明"


def confidence(coverage_ratio: float, valid_count: int) -> LifecycleConfidence:
    if coverage_ratio >= 0.75 and valid_count >= 20:
        return "high"
    if coverage_ratio >= 0.55 and valid_count >= 10:
        return "medium"
    return "low"


def build_industry_points(
    *,
    identities: Sequence[IndustryIdentity],
    memberships: Sequence[MembershipInterval],
    evaluation_dates: Sequence[date],
    structures: Mapping[date, Mapping[str, StructureState]],
    amount_shares: Mapping[str, float],
) -> tuple[IndustryLifecyclePoint, ...]:
    histories: dict[str, list[tuple[date, float, float, int, int]]] = defaultdict(list)
    for observed in evaluation_dates:
        by_industry: dict[str, list[str]] = defaultdict(list)
        for membership in memberships:
            if membership.effective_from <= observed and (
                membership.effective_to is None or observed < membership.effective_to
            ):
                by_industry[membership.industry_code].append(membership.instrument_id)
        daily = structures.get(observed, {})
        for identity in identities:
            members = by_industry.get(identity.industry_code, [])
            valid = [daily[item] for item in members if item in daily]
            if valid:
                histories[identity.industry_code].append(
                    (
                        observed,
                        100.0 * sum(item.strong for item in valid) / len(valid),
                        100.0 * sum(item.low for item in valid) / len(valid),
                        len(members),
                        len(valid),
                    )
                )
    return tuple(
        _point(identity, histories.get(identity.industry_code, []), amount_shares)
        for identity in identities
    )


def _point(
    identity: IndustryIdentity,
    history: Sequence[tuple[date, float, float, int, int]],
    amount_shares: Mapping[str, float],
) -> IndustryLifecyclePoint:
    gaps: list[str] = []
    if not history:
        return IndustryLifecyclePoint(
            industry_code=identity.industry_code,
            industry_name=identity.industry_name,
            stage="方向未明",
            confidence="low",
            eligible_member_count=0,
            valid_member_count=0,
            coverage_ratio=0,
            known_gaps=("insufficient_price_history",),
        )
    smoothed = [
        (
            item[0],
            median(value[1] for value in history[max(0, index - 2) : index + 1]),
            median(value[2] for value in history[max(0, index - 2) : index + 1]),
            item[3],
            item[4],
        )
        for index, item in enumerate(history)
    ]
    current = smoothed[-1]
    coverage = current[4] / current[3] if current[3] else 0.0
    level = confidence(coverage, current[4])
    enough = len(smoothed) >= 20
    delta_strong = current[1] - smoothed[-6][1] if enough else None
    delta_low = current[2] - smoothed[-6][2] if enough else None
    peak = max(item[1] for item in smoothed[-20:]) if enough else None
    stage = _history_stage(smoothed, len(smoothed) - 1)
    previous_stage = _history_stage(smoothed, len(smoothed) - 2)
    if not enough:
        gaps.append("insufficient_lifecycle_history")
    if level == "low":
        gaps.append("member_coverage_below_threshold")
    return IndustryLifecyclePoint(
        industry_code=identity.industry_code,
        industry_name=identity.industry_name,
        stage=stage,
        confidence=level,
        strong_participation=current[1] if level != "low" else None,
        low_participation=current[2] if level != "low" else None,
        strong_change_5d=delta_strong,
        low_change_5d=delta_low,
        strong_peak_20d=peak,
        strong_drawdown_20d=peak - current[1] if peak is not None else None,
        amount_share_20d=amount_shares.get(identity.industry_code),
        eligible_member_count=current[3],
        valid_member_count=current[4],
        coverage_ratio=coverage,
        recently_transitioned=stage != previous_stage,
        trajectory=tuple(
            LifecycleTrajectoryPoint(
                trade_date=item[0],
                strong_participation=item[1],
                low_participation=item[2],
            )
            for item in smoothed[-20:]
        ),
        known_gaps=tuple(gaps),
    )


def _history_stage(
    history: Sequence[tuple[date, float, float, int, int]],
    index: int,
) -> LifecycleStage:
    if index < 19:
        return "方向未明"
    current = history[index]
    coverage = current[4] / current[3] if current[3] else 0.0
    if confidence(coverage, current[4]) == "low":
        return "方向未明"
    peak = max(item[1] for item in history[index - 19 : index + 1])
    return lifecycle_stage(
        strong=current[1],
        low=current[2],
        delta_strong=current[1] - history[index - 5][1],
        delta_low=current[2] - history[index - 5][2],
        peak_strong=peak,
    )


__all__ = [
    "IndustryIdentity",
    "MembershipInterval",
    "build_industry_points",
    "confidence",
    "lifecycle_stage",
]
