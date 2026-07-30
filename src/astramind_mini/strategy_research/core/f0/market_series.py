"""Common-session market-series selection shared by F0 operators."""

from __future__ import annotations

import math
from collections.abc import Sequence
from datetime import date

from .computation_semantics import F0_MARKET_OPERATOR_SEMANTICS as _SEMANTICS
from .inputs import F0InputBundle, F0MarketBar, visible_market_bars
from .reasons import F0Reason


def bar_index(bundle: F0InputBundle) -> dict[tuple[str, date], F0MarketBar]:
    if _SEMANTICS.market_bar_selection != "maximum_authoritative_available_at":
        raise RuntimeError("unsupported F0 market bar selection semantics")
    grouped: dict[tuple[str, date], list[F0MarketBar]] = {}
    for bar in visible_market_bars(bundle):
        key = (bar.instrument_id, bar.market_date)
        grouped.setdefault(key, []).append(bar)
    result: dict[tuple[str, date], F0MarketBar] = {}
    for key, revisions in grouped.items():
        latest_available = max(item.available_at for item in revisions)
        latest = [item for item in revisions if item.available_at == latest_available]
        selected = latest[0]
        if any(item != selected for item in latest[1:]):
            _validate_equal_time_policy()
            raise ValueError("market bars conflict at the latest availability time")
        result[key] = selected
    return result


def _validate_equal_time_policy() -> None:
    if (
        _SEMANTICS.market_bar_equal_time_policy
        != "identical_record_deduplicates_otherwise_fail_closed"
    ):
        raise RuntimeError("unsupported F0 equal-time market bar policy")


def window_session(sessions: Sequence[date], offset: int) -> date | None:
    return sessions[-offset - 1] if len(sessions) > offset else None


def close_value(
    bars: dict[tuple[str, date], F0MarketBar],
    instrument_id: str,
    day: date,
) -> float | None:
    bar = bars.get((instrument_id, day))
    return bar.research_close if bar is not None else None


def simple_return(previous: float, current: float) -> float:
    if _SEMANTICS.simple_return_operator != "current_close_div_previous_close_minus_one":
        raise RuntimeError("unsupported F0 simple-return operator")
    return current / previous - 1


def simple_returns(
    bars: dict[tuple[str, date], F0MarketBar],
    sessions: Sequence[date],
    instrument_id: str,
    count: int,
) -> list[float] | F0Reason:
    if len(sessions) < count + 1:
        return F0Reason.COMMON_SESSION_WINDOW_INCOMPLETE
    closes = [
        close_value(bars, instrument_id, day) for day in sessions[-count - 1 :]
    ]
    if any(value is None for value in closes):
        return F0Reason.COMMON_SESSION_WINDOW_INCOMPLETE
    numeric = [float(value) for value in closes if value is not None]
    if any(not math.isfinite(value) for value in numeric):
        return F0Reason.NON_FINITE_RESULT
    return [
        simple_return(numeric[index - 1], numeric[index])
        for index in range(1, len(numeric))
    ]


__all__ = [
    "bar_index",
    "close_value",
    "simple_return",
    "simple_returns",
    "window_session",
]
