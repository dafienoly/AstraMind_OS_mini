"""Deterministic, no-look-ahead features for heat and relative rotation."""

from __future__ import annotations

import math
import statistics
from collections.abc import Mapping
from datetime import date

from .source import IndustryBar, ProductionHistory

HEAT_FEATURES = (
    "industry_return_1d",
    "industry_return_5d",
    "industry_return_20d",
    "industry_return_60d",
    "benchmark_return_1d",
    "benchmark_return_5d",
    "benchmark_return_20d",
    "benchmark_return_60d",
    "relative_return_1d",
    "relative_return_5d",
    "relative_return_20d",
    "relative_return_60d",
    "volatility_20d",
    "amount_share",
    "amount_ratio_20d",
    "breadth_ratio",
    "coverage_ratio",
    "price_earnings",
    "price_book",
)
ROTATION_FEATURES = (
    "relative_return_5d",
    "relative_return_20d",
    "relative_return_60d",
    "relative_trend",
    "relative_momentum_5d",
    "raw_z_trend",
    "raw_z_momentum",
    "amount_share",
    "breadth_ratio",
    "coverage_ratio",
    "volatility_20d",
)


class FeaturePanel:
    def __init__(self, history: ProductionHistory) -> None:
        self.codes, self.calendar, self._bars = _organize(history)
        self._benchmark = history.benchmark_closes
        self._breadth = history.breadth
        self._amount_shares = _amount_shares(self.codes, self.calendar, self._bars)
        self._rotation = _rotation_features(self.codes, self.calendar, self._bars)

    def feature_names(self, family: str) -> tuple[str, ...]:
        if family == "industry_heat":
            return HEAT_FEATURES
        if family == "industry_rotation":
            return ROTATION_FEATURES
        raise ValueError(f"unsupported production model family: {family}")

    def values(
        self,
        family: str,
        code: str,
        index: int,
    ) -> tuple[float | None, ...]:
        day = self.calendar[index]
        industry = self._bars[code]
        base = {
            **{
                f"industry_return_{horizon}d": _return(industry, self.calendar, index, horizon)
                for horizon in (1, 5, 20, 60)
            },
            **{
                f"benchmark_return_{horizon}d": _return(
                    self._benchmark,
                    self.calendar,
                    index,
                    horizon,
                )
                for horizon in (1, 5, 20, 60)
            },
        }
        for horizon in (1, 5, 20, 60):
            asset = base[f"industry_return_{horizon}d"]
            benchmark = base[f"benchmark_return_{horizon}d"]
            base[f"relative_return_{horizon}d"] = (
                asset - benchmark if asset is not None and benchmark is not None else None
            )
        bar = industry[day]
        breadth = self._breadth.get((code, day))
        compared = breadth.advancing_count + breadth.declining_count if breadth is not None else 0
        base.update(
            {
                "volatility_20d": _volatility(industry, self.calendar, index, 20),
                "amount_share": self._amount_shares.get((code, day)),
                "amount_ratio_20d": _amount_ratio(industry, self.calendar, index, 20),
                "breadth_ratio": (
                    breadth.advancing_count / compared if breadth is not None and compared else None
                ),
                "coverage_ratio": (
                    breadth.covered_count / breadth.member_count
                    if breadth is not None and breadth.member_count
                    else None
                ),
                "price_earnings": bar.price_earnings,
                "price_book": bar.price_book,
            }
        )
        trend, momentum, trend_z, momentum_z = self._rotation.get(
            (code, day),
            (None, None, None, None),
        )
        base.update(
            {
                "relative_trend": trend,
                "relative_momentum_5d": momentum,
                "raw_z_trend": trend_z,
                "raw_z_momentum": momentum_z,
            }
        )
        return tuple(base[name] for name in self.feature_names(family))

    def label(self, code: str, index: int, horizon: int) -> float:
        future = index + horizon
        industry_return = _return(self._bars[code], self.calendar, future, horizon)
        benchmark_return = _return(self._benchmark, self.calendar, future, horizon)
        if industry_return is None or benchmark_return is None:
            raise ValueError("future label window is incomplete")
        return industry_return - benchmark_return


def _organize(
    history: ProductionHistory,
) -> tuple[tuple[str, ...], tuple[date, ...], dict[str, dict[date, IndustryBar]]]:
    typed: dict[str, dict[date, IndustryBar]] = {}
    for bar in history.industry_bars:
        if bar.trade_date in typed.setdefault(bar.industry_code, {}):
            raise ValueError(f"duplicate industry bar: {bar.industry_code}:{bar.trade_date}")
        typed[bar.industry_code][bar.trade_date] = bar
    codes = tuple(sorted(typed))
    shared = set(history.benchmark_closes)
    for values in typed.values():
        shared.intersection_update(values)
    calendar = tuple(sorted(shared))
    if len(codes) < 3 or len(calendar) < 81:
        raise ValueError("industry feature panel history is incomplete")
    return codes, calendar, typed


def _return(
    values: Mapping[date, object],
    calendar: tuple[date, ...],
    index: int,
    horizon: int,
) -> float | None:
    if index < horizon:
        return None
    current, previous = values.get(calendar[index]), values.get(calendar[index - horizon])
    current_value = _close(current)
    previous_value = _close(previous)
    if current_value is None or previous_value is None or previous_value <= 0:
        return None
    return current_value / previous_value - 1.0


def _volatility(
    bars: Mapping[date, IndustryBar],
    calendar: tuple[date, ...],
    index: int,
    window: int,
) -> float | None:
    if index < window:
        return None
    returns = tuple(
        _return(bars, calendar, position, 1) for position in range(index - window + 1, index + 1)
    )
    if any(value is None for value in returns):
        return None
    return statistics.stdev(value for value in returns if value is not None)


def _amount_ratio(
    bars: Mapping[date, IndustryBar],
    calendar: tuple[date, ...],
    index: int,
    window: int,
) -> float | None:
    if index + 1 < window:
        return None
    values = [
        getattr(bars[calendar[position]], "amount", None)
        for position in range(index - window + 1, index + 1)
    ]
    if any(value is None for value in values):
        return None
    observed = [float(value) for value in values if value is not None]
    average = statistics.fmean(observed)
    return observed[-1] / average - 1.0 if average > 0 else None


def _amount_shares(
    codes: tuple[str, ...],
    calendar: tuple[date, ...],
    bars: Mapping[str, Mapping[date, IndustryBar]],
) -> dict[tuple[str, date], float]:
    result = {}
    for day in calendar:
        amounts = {code: getattr(bars[code][day], "amount", None) for code in codes}
        total = sum(float(value) for value in amounts.values() if value is not None and value > 0)
        if total <= 0:
            continue
        result.update(
            {
                (code, day): float(value) / total
                for code, value in amounts.items()
                if value is not None and value >= 0
            }
        )
    return result


def _close(value: object | None) -> float | None:
    if value is None:
        return None
    observed = getattr(value, "close", value)
    return float(observed) if isinstance(observed, int | float) and observed > 0 else None


def _rotation_features(
    codes: tuple[str, ...],
    calendar: tuple[date, ...],
    bars: Mapping[str, Mapping[date, IndustryBar]],
) -> dict[tuple[str, date], tuple[float, float | None, float | None, float | None]]:
    states = dict.fromkeys(codes, 0.0)
    fast = dict(states)
    slow = dict(states)
    histories: dict[str, list[float]] = {code: [] for code in codes}
    raw: dict[date, dict[str, tuple[float, float | None]]] = {}
    for index, day in enumerate(calendar[1:], start=1):
        returns = {}
        for code in codes:
            current = _close(bars[code][day])
            previous = _close(bars[code][calendar[index - 1]])
            if current is None or previous is None:
                raise ValueError("complete rotation panel contains an invalid close")
            returns[code] = math.log(current / previous)
        benchmark = statistics.fmean(returns.values())
        raw[day] = {}
        for code, value in returns.items():
            states[code] += value - benchmark
            fast[code] += 2.0 / 21.0 * (states[code] - fast[code])
            slow[code] += 2.0 / 61.0 * (states[code] - slow[code])
            trend = fast[code] - slow[code]
            histories[code].append(trend)
            momentum = (
                histories[code][-1] - histories[code][-6] if len(histories[code]) > 5 else None
            )
            raw[day][code] = (trend, momentum)
    return _standardize_rotation(raw, codes)


def _standardize_rotation(
    raw: Mapping[date, Mapping[str, tuple[float, float | None]]],
    codes: tuple[str, ...],
) -> dict[tuple[str, date], tuple[float, float | None, float | None, float | None]]:
    result = {}
    for day, values in raw.items():
        trends = {code: values[code][0] for code in codes}
        momentums: dict[str, float] = {}
        for code in codes:
            momentum = values[code][1]
            if momentum is not None:
                momentums[code] = momentum
        trend_z = _robust_z(trends)
        momentum_z = _robust_z(momentums) if len(momentums) == len(codes) else {}
        for code in codes:
            trend, momentum = values[code]
            result[(code, day)] = (trend, momentum, trend_z.get(code), momentum_z.get(code))
    return result


def _robust_z(values: Mapping[str, float]) -> dict[str, float]:
    center = statistics.median(values.values())
    mad = statistics.median(abs(value - center) for value in values.values())
    denominator = 1.4826 * mad or statistics.pstdev(values.values())
    if denominator < 1e-12:
        return {}
    return {key: (value - center) / denominator for key, value in values.items()}


__all__ = ["HEAT_FEATURES", "ROTATION_FEATURES", "FeaturePanel"]
