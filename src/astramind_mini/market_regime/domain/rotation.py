"""Pure deterministic relative-rotation engine."""

from __future__ import annotations

import math
import statistics
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime

from ..contracts import (
    MarketRotationSnapshot,
    Quadrant,
    RotationEvent,
    RotationFormula,
    RotationPoint,
)
from .identity import content_hash

DISPLAY_TRANSFORM_VERSION = "rotation-display-tanh-v1.0.0"


@dataclass(frozen=True, slots=True)
class IndustryCloseSeries:
    industry_code: str
    industry_name: str
    closes: Mapping[date, float]
    constituent_counts: Mapping[date, int]


def build_rotation_snapshot(
    *,
    data_snapshot_id: str,
    as_of: datetime,
    created_at: datetime,
    calendar: Sequence[date],
    industries: Sequence[IndustryCloseSeries],
    formula: RotationFormula,
    known_gaps: Sequence[str] = (),
) -> MarketRotationSnapshot:
    ordered = tuple(sorted(industries, key=lambda item: item.industry_code))
    if len(ordered) < 3 or len({item.industry_code for item in ordered}) != len(ordered):
        raise ValueError("轮动行业注册表不足或身份重复")
    required = formula.warmup_sessions + 1
    if formula.output_sessions + formula.momentum_window >= formula.warmup_sessions:
        raise ValueError("轮动预热区间不足以覆盖输出和动量窗口")
    dates = tuple(sorted(set(calendar)))
    if len(dates) < required:
        raise ValueError(f"轮动计算至少需要 {required} 个交易日")
    panel_dates = dates[-required:]
    _validate_panel(ordered, panel_dates, formula)
    raw_trend, raw_momentum = _raw_coordinates(ordered, panel_dates, formula)
    scored = _score_coordinates(raw_trend, raw_momentum, formula)
    output_dates = panel_dates[-formula.output_sessions :]
    points = _points(ordered, output_dates, scored, formula)
    events = _events(points, formula)
    identity = {
        "data_snapshot_id": data_snapshot_id,
        "as_of": as_of,
        "formula": formula.model_dump(mode="json"),
        "dates": output_dates,
        "points": [point.model_dump(mode="json") for point in points],
        "events": [event.model_dump(mode="json") for event in events],
        "known_gaps": sorted(known_gaps),
    }
    digest = content_hash(identity)
    return MarketRotationSnapshot(
        rotation_snapshot_id="rotation:" + digest,
        data_snapshot_id=data_snapshot_id,
        as_of=as_of,
        benchmark_id=formula.benchmark_id,
        benchmark_definition_version=formula.benchmark_definition_version,
        formula=formula,
        taxonomy="SW",
        taxonomy_version="SW2021",
        industry_count=len(ordered),
        covered_industry_count=len(ordered),
        coverage_rule="required index panel 100%; active constituents >= 3",
        date_range=(output_dates[0], output_dates[-1]),
        dates=output_dates,
        points=points,
        events=events,
        created_at=created_at,
        content_hash=digest,
        known_gaps=tuple(sorted(known_gaps)),
    )


def _validate_panel(
    industries: Sequence[IndustryCloseSeries],
    dates: Sequence[date],
    formula: RotationFormula,
) -> None:
    for industry in industries:
        for day in dates:
            close = industry.closes.get(day)
            if close is None or not math.isfinite(close) or close <= 0:
                raise ValueError(f"行业指数面板缺失或价格无效：{industry.industry_code}:{day}")
        for day in dates[-formula.output_sessions :]:
            if industry.constituent_counts.get(day, 0) < formula.minimum_constituent_count:
                raise ValueError(f"行业有效成分不足：{industry.industry_code}:{day}")


def _raw_coordinates(
    industries: Sequence[IndustryCloseSeries],
    dates: Sequence[date],
    formula: RotationFormula,
) -> tuple[dict[date, dict[str, float]], dict[date, dict[str, float]]]:
    relative_states = {item.industry_code: 0.0 for item in industries}
    fast = dict(relative_states)
    slow = dict(relative_states)
    trend_history: dict[str, list[float]] = {item.industry_code: [] for item in industries}
    trend_by_date: dict[date, dict[str, float]] = {}
    momentum_by_date: dict[date, dict[str, float]] = {}
    alpha_fast = 2.0 / (formula.fast_window + 1)
    alpha_slow = 2.0 / (formula.slow_window + 1)
    for index, day in enumerate(dates[1:], start=1):
        returns = {
            item.industry_code: math.log(item.closes[day] / item.closes[dates[index - 1]])
            for item in industries
        }
        benchmark = statistics.fmean(returns.values())
        trend_by_date[day], momentum_by_date[day] = {}, {}
        for code, value in returns.items():
            relative_states[code] += value - benchmark
            fast[code] += alpha_fast * (relative_states[code] - fast[code])
            slow[code] += alpha_slow * (relative_states[code] - slow[code])
            trend = fast[code] - slow[code]
            history = trend_history[code]
            history.append(trend)
            trend_by_date[day][code] = trend
            if len(history) > formula.momentum_window:
                momentum_by_date[day][code] = trend - history[-formula.momentum_window - 1]
    return trend_by_date, momentum_by_date


def _score_coordinates(
    trends: Mapping[date, Mapping[str, float]],
    momentums: Mapping[date, Mapping[str, float]],
    formula: RotationFormula,
) -> dict[date, dict[str, tuple[float, float, bool, float, float]]]:
    result: dict[date, dict[str, tuple[float, float, bool, float, float]]] = {}
    for day in sorted(set(trends) & set(momentums)):
        if len(momentums[day]) != len(trends[day]):
            continue
        trend_z = _robust_z(trends[day])
        momentum_z = _robust_z(momentums[day])
        result[day] = {}
        for code in sorted(trend_z):
            tx, my = trend_z[code], momentum_z[code]
            overflow = abs(tx) > formula.clip_z or abs(my) > formula.clip_z
            x = 100 + formula.scale * max(-formula.clip_z, min(formula.clip_z, tx))
            y = 100 + formula.scale * max(-formula.clip_z, min(formula.clip_z, my))
            result[day][code] = (
                round(x, formula.rounding_decimals),
                round(y, formula.rounding_decimals),
                overflow,
                round(tx, formula.rounding_decimals),
                round(my, formula.rounding_decimals),
            )
    return result


def _robust_z(values: Mapping[str, float]) -> dict[str, float]:
    ordered = tuple(values.values())
    center = statistics.median(ordered)
    mad = statistics.median(abs(value - center) for value in ordered)
    denominator = 1.4826 * mad
    if denominator < 1e-12:
        denominator = statistics.pstdev(ordered)
    if denominator < 1e-12:
        raise ValueError("轮动横截面方差为零，拒绝生成中心占位点")
    return {code: (value - center) / denominator for code, value in values.items()}


def _points(
    industries: Sequence[IndustryCloseSeries],
    dates: Sequence[date],
    scored: Mapping[date, Mapping[str, tuple[float, float, bool, float, float]]],
    formula: RotationFormula,
) -> tuple[RotationPoint, ...]:
    names = {item.industry_code: item.industry_name for item in industries}
    counts = {item.industry_code: item.constituent_counts for item in industries}
    result: list[RotationPoint] = []
    previous: dict[str, tuple[float, float]] = {}
    for day in dates:
        if day not in scored or len(scored[day]) != len(industries):
            raise ValueError(f"轮动输出日期缺少完整坐标：{day}")
        for code in sorted(scored[day]):
            x, y, overflow, raw_z_trend, raw_z_momentum = scored[day][code]
            old_x, old_y = previous.get(code, (x, y))
            result.append(
                RotationPoint(
                    industry_code=code,
                    industry_name=names[code],
                    trade_date=day,
                    relative_trend=x,
                    relative_momentum=y,
                    quadrant=_quadrant(x, y),
                    coverage=formula.required_industry_coverage,
                    constituent_count=counts[code][day],
                    direction_x=round(x - old_x, formula.rounding_decimals),
                    direction_y=round(y - old_y, formula.rounding_decimals),
                    overflow=overflow,
                    raw_z_trend=raw_z_trend,
                    raw_z_momentum=raw_z_momentum,
                    display_transform_version=DISPLAY_TRANSFORM_VERSION,
                )
            )
            previous[code] = (x, y)
    return tuple(result)


def _quadrant(x: float, y: float) -> Quadrant:
    if x >= 100 and y >= 100:
        return "leading"
    if x >= 100:
        return "weakening"
    if y >= 100:
        return "improving"
    return "lagging"


def _events(points: Sequence[RotationPoint], formula: RotationFormula) -> tuple[RotationEvent, ...]:
    by_industry: dict[str, list[RotationPoint]] = {}
    for point in points:
        by_industry.setdefault(point.industry_code, []).append(point)
    result = []
    for code, history in sorted(by_industry.items()):
        stable: Quadrant | None = None
        candidate: tuple[Quadrant, date, int] | None = None
        for point in history:
            current = _stable_quadrant(point, formula.neutral_band)
            if current is None or current == stable:
                candidate = None
                continue
            if candidate is None or candidate[0] != current:
                candidate = (current, point.trade_date, 1)
                continue
            candidate = (current, candidate[1], candidate[2] + 1)
            if candidate[2] == formula.confirmation_sessions:
                if stable is not None:
                    result.append(
                        RotationEvent(
                            industry_code=code,
                            industry_name=point.industry_name,
                            from_quadrant=stable,
                            to_quadrant=current,
                            first_cross_date=candidate[1],
                            confirmed_date=point.trade_date,
                            formula_version=formula.formula_version,
                        )
                    )
                stable, candidate = current, None
    return tuple(result)


def _stable_quadrant(point: RotationPoint, band: float) -> Quadrant | None:
    if abs(point.relative_trend - 100) <= band or abs(point.relative_momentum - 100) <= band:
        return None
    return point.quadrant


__all__ = [
    "DISPLAY_TRANSFORM_VERSION",
    "IndustryCloseSeries",
    "build_rotation_snapshot",
]
