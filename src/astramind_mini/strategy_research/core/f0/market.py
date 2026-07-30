"""Exact common-session market formulas for astramind-f0-v1."""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from datetime import date
from itertools import pairwise
from statistics import fmean, median, stdev

from .computation_semantics import F0_MARKET_OPERATOR_SEMANTICS as _SEMANTICS
from .inputs import F0InputBundle, F0MarketBar
from .market_reductions import (
    compound_returns,
    cross_section_return,
    incomplete_ols_rows_are_dropped,
    industry_at,
    industry_relative_period,
    ols_residual_reversal,
)
from .market_series import (
    bar_index as _bar_index,
)
from .market_series import (
    close_value as _close,
)
from .market_series import (
    simple_return,
)
from .market_series import (
    simple_returns as _returns,
)
from .market_series import (
    window_session as _window,
)
from .reasons import F0Reason
from .result import FormulaResult, missing, not_applicable, observed

MARKET_FEATURES = (
    "MOM_20_5",
    "MOM_60_5",
    "MOM_120_20",
    "INDUSTRY_REL_MOM_60_5",
    "REV_5",
    "RESIDUAL_REV_20",
    "REALIZED_VOL_20",
    "DOWNSIDE_VOL_60",
    "LOG_MEDIAN_AMOUNT_20",
    "TURNOVER_MEAN_20",
    "AMIHUD_20",
)


def evaluate_market_features(
    bundle: F0InputBundle,
    instrument_id: str,
) -> dict[str, FormulaResult]:
    bars = _bar_index(bundle)
    sessions = tuple(
        day for day in bundle.common_sessions if day <= bundle.core_input.decision_date
    )
    momentum = {
        feature: (old_offset, new_offset)
        for feature, old_offset, new_offset in (
            _SEMANTICS.momentum_windows
        )
    }
    return {
        "MOM_20_5": _close_ratio(bars, sessions, instrument_id, *momentum["MOM_20_5"]),
        "MOM_60_5": _close_ratio(bars, sessions, instrument_id, *momentum["MOM_60_5"]),
        "MOM_120_20": _close_ratio(
            bars,
            sessions,
            instrument_id,
            *momentum["MOM_120_20"],
        ),
        "INDUSTRY_REL_MOM_60_5": _industry_relative_momentum(bundle, bars, sessions, instrument_id),
        "REV_5": _reversal(bars, sessions, instrument_id),
        "RESIDUAL_REV_20": _residual_reversal(bundle, bars, sessions, instrument_id),
        "REALIZED_VOL_20": _realized_vol(bars, sessions, instrument_id),
        "DOWNSIDE_VOL_60": _downside_vol(bars, sessions, instrument_id),
        "LOG_MEDIAN_AMOUNT_20": _last_twenty_stat(
            bars,
            sessions,
            instrument_id,
            lambda items: math.log1p(median(items)),
            "amount_cny",
        ),
        "TURNOVER_MEAN_20": _last_twenty_stat(
            bars,
            sessions,
            instrument_id,
            fmean,
            "turnover_rate",
        ),
        "AMIHUD_20": _amihud(bars, sessions, instrument_id),
    }


def _close_ratio(
    bars: dict[tuple[str, date], F0MarketBar],
    sessions: Sequence[date],
    instrument_id: str,
    old_offset: int,
    new_offset: int,
) -> FormulaResult:
    old_day, new_day = _window(sessions, old_offset), _window(sessions, new_offset)
    if old_day is None or new_day is None:
        return missing(F0Reason.COMMON_SESSION_WINDOW_INCOMPLETE)
    old, new = _close(bars, instrument_id, old_day), _close(bars, instrument_id, new_day)
    if old is None or new is None:
        return missing(F0Reason.COMMON_SESSION_WINDOW_INCOMPLETE)
    if not math.isfinite(old) or not math.isfinite(new):
        return missing(F0Reason.NON_FINITE_RESULT)
    return observed(simple_return(old, new))


def _reversal(
    bars: dict[tuple[str, date], F0MarketBar],
    sessions: Sequence[date],
    instrument_id: str,
) -> FormulaResult:
    old_day = _window(sessions, _SEMANTICS.reversal_window_sessions)
    current_day = _window(sessions, 0)
    if old_day is None or current_day is None:
        return missing(F0Reason.COMMON_SESSION_WINDOW_INCOMPLETE)
    old = _close(bars, instrument_id, old_day)
    current = _close(bars, instrument_id, current_day)
    if old is None or current is None:
        return missing(F0Reason.COMMON_SESSION_WINDOW_INCOMPLETE)
    if not math.isfinite(old) or not math.isfinite(current):
        return missing(F0Reason.NON_FINITE_RESULT)
    return observed(-simple_return(old, current))


def _realized_vol(
    bars: dict[tuple[str, date], F0MarketBar],
    sessions: Sequence[date],
    instrument_id: str,
) -> FormulaResult:
    returns = _returns(
        bars,
        sessions,
        instrument_id,
        _SEMANTICS.realized_volatility_window_returns,
    )
    if isinstance(returns, F0Reason):
        return missing(returns)
    log_returns = [math.log1p(value) for value in returns]
    return observed(
        math.sqrt(_SEMANTICS.annualization_sessions) * stdev(log_returns)
    )


def _downside_vol(
    bars: dict[tuple[str, date], F0MarketBar],
    sessions: Sequence[date],
    instrument_id: str,
) -> FormulaResult:
    returns = _returns(
        bars,
        sessions,
        instrument_id,
        _SEMANTICS.downside_volatility_window_returns,
    )
    if isinstance(returns, F0Reason):
        return missing(returns)
    return observed(
        math.sqrt(
            _SEMANTICS.annualization_sessions
            * fmean(min(value, 0) ** 2 for value in returns)
        )
    )


def _last_twenty_stat(
    bars: dict[tuple[str, date], F0MarketBar],
    sessions: Sequence[date],
    instrument_id: str,
    statistic: Callable[[Sequence[float]], float],
    field: str,
) -> FormulaResult:
    window = _SEMANTICS.liquidity_window_sessions
    if len(sessions) < window:
        return missing(F0Reason.COMMON_SESSION_WINDOW_INCOMPLETE)
    values: list[float] = []
    for day in sessions[-window:]:
        bar = bars.get((instrument_id, day))
        value = getattr(bar, field) if bar is not None else None
        if value is None:
            return missing(F0Reason.COMMON_SESSION_WINDOW_INCOMPLETE)
        numeric = float(value)
        if not math.isfinite(numeric):
            return missing(F0Reason.NON_FINITE_RESULT)
        values.append(numeric)
    return observed(statistic(values))


def _amihud(
    bars: dict[tuple[str, date], F0MarketBar],
    sessions: Sequence[date],
    instrument_id: str,
) -> FormulaResult:
    window = _SEMANTICS.liquidity_window_sessions
    returns = _returns(bars, sessions, instrument_id, window)
    if isinstance(returns, F0Reason):
        return missing(returns)
    ratios: list[float] = []
    for day, daily_return in zip(sessions[-window:], returns, strict=True):
        bar = bars.get((instrument_id, day))
        if bar is None or bar.amount_cny is None or bar.amount_cny <= 0:
            return missing(F0Reason.AMIHUD_COVERAGE_INCOMPLETE)
        if not math.isfinite(bar.amount_cny):
            return missing(F0Reason.NON_FINITE_RESULT)
        ratios.append(abs(daily_return) / bar.amount_cny)
    return observed(
        math.log1p(_SEMANTICS.amihud_scale * fmean(ratios))
    )


def _industry_relative_momentum(
    bundle: F0InputBundle,
    bars: dict[tuple[str, date], F0MarketBar],
    sessions: Sequence[date],
    instrument_id: str,
) -> FormulaResult:
    if industry_at(bundle, instrument_id, bundle.core_input.decision_date) is None:
        return not_applicable(F0Reason.INDUSTRY_MEMBERSHIP_UNAVAILABLE)
    old_offset, new_offset = _SEMANTICS.industry_relative_momentum_window
    own = _close_ratio(bars, sessions, instrument_id, old_offset, new_offset)
    if own.value is None:
        return own
    period = industry_relative_period(sessions, old_offset, new_offset)
    if period is None:
        return missing(F0Reason.COMMON_SESSION_WINDOW_INCOMPLETE)
    daily_returns: list[float] = []
    for previous_day, day in pairwise(period):
        industry = industry_at(bundle, instrument_id, day)
        if industry is None:
            return not_applicable(F0Reason.INDUSTRY_MEMBERSHIP_UNAVAILABLE)
        daily_return = cross_section_return(
            bundle,
            bars,
            previous_day,
            day,
            industry,
        )
        if isinstance(daily_return, F0Reason):
            return missing(daily_return)
        daily_returns.append(daily_return)
    return observed(own.value - compound_returns(daily_returns))


def _residual_reversal(
    bundle: F0InputBundle,
    bars: dict[tuple[str, date], F0MarketBar],
    sessions: Sequence[date],
    instrument_id: str,
) -> FormulaResult:
    if industry_at(bundle, instrument_id, bundle.core_input.decision_date) is None:
        return not_applicable(F0Reason.INDUSTRY_MEMBERSHIP_UNAVAILABLE)
    window = _SEMANTICS.residual_window_returns
    if len(sessions) < window + 1:
        return missing(F0Reason.COMMON_SESSION_WINDOW_INCOMPLETE)
    rows: list[tuple[float, float, float]] = []
    period = sessions[-window - 1 :]
    for previous_day, day in pairwise(period):
        industry = industry_at(bundle, instrument_id, day)
        if industry is None:
            return not_applicable(F0Reason.INDUSTRY_MEMBERSHIP_UNAVAILABLE)
        previous = _close(bars, instrument_id, previous_day)
        current = _close(bars, instrument_id, day)
        if (
            previous is not None
            and current is not None
            and (not math.isfinite(previous) or not math.isfinite(current))
        ):
            return missing(F0Reason.NON_FINITE_RESULT)
        u0_return = cross_section_return(bundle, bars, previous_day, day)
        industry_return = cross_section_return(
            bundle,
            bars,
            previous_day,
            day,
            industry,
        )
        incomplete = (
            previous is None
            or current is None
            or isinstance(u0_return, F0Reason)
            or isinstance(industry_return, F0Reason)
        )
        if incomplete and incomplete_ols_rows_are_dropped():
            continue
        if (
            previous is not None
            and current is not None
            and not isinstance(u0_return, F0Reason)
            and not isinstance(industry_return, F0Reason)
        ):
            rows.append(
                (
                    simple_return(previous, current),
                    u0_return,
                    industry_return,
                )
            )
    result = ols_residual_reversal(rows)
    if isinstance(result, F0Reason):
        return missing(result)
    return observed(result)


__all__ = ["MARKET_FEATURES", "evaluate_market_features"]
