"""Pure lifecycle structure calculations.

The method is a reproducible research hypothesis, not an execution signal or a
claim of independently validated predictive performance.
"""

from __future__ import annotations

import math
from bisect import bisect_left, bisect_right
from collections import defaultdict, deque
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date

from .lifecycle_aggregation import (
    IndustryIdentity,
    MembershipInterval,
    build_industry_points,
    confidence,
    lifecycle_stage,
)

METHOD_VERSION = "lifecycle-structure-v1.0.0"


@dataclass(frozen=True)
class PriceObservation:
    instrument_id: str
    trade_date: date
    close: float


@dataclass(frozen=True)
class StockStructure:
    strong: bool
    low: bool


def compute_stock_structures(
    observations: Iterable[PriceObservation],
    evaluation_dates: Sequence[date],
    *,
    sessions: Sequence[date] | None = None,
) -> dict[date, dict[str, StockStructure]]:
    """Calculate point-in-time stock structure states on bounded evaluation dates."""
    wanted = set(evaluation_dates)
    pending: dict[date, dict[str, tuple[float, float, float, float]]] = {
        item: {} for item in evaluation_dates
    }
    if sessions is None:
        by_instrument: dict[str, dict[date, float]] = defaultdict(dict)
        all_dates: set[date] = set()
        for item in observations:
            if item.close > 0 and math.isfinite(item.close):
                by_instrument[item.instrument_id][item.trade_date] = item.close
                all_dates.add(item.trade_date)
        resolved_sessions = sorted(all_dates)
        for instrument_id, instrument_values in by_instrument.items():
            _instrument_structures(
                instrument_id, instrument_values, resolved_sessions, wanted, pending
            )
    else:
        current_id: str | None = None
        values: dict[date, float] = {}
        for item in observations:
            if current_id is not None and item.instrument_id != current_id:
                _instrument_structures(current_id, values, sessions, wanted, pending)
                values = {}
            current_id = item.instrument_id
            if item.close > 0 and math.isfinite(item.close):
                values[item.trade_date] = item.close
        if current_id is not None:
            _instrument_structures(current_id, values, sessions, wanted, pending)
    return _resolve_cross_section(pending)


def _instrument_structures(
    instrument_id: str,
    values: Mapping[date, float],
    sessions: Sequence[date],
    wanted: set[date],
    output: dict[date, dict[str, tuple[float, float, float, float]]],
) -> None:
    history: deque[float] = deque(maxlen=252)
    log_history: deque[float] = deque(maxlen=121)
    consecutive = 0
    ema20: float | None = None
    ema60: float | None = None
    ema20_history: deque[float] = deque(maxlen=6)
    vol20: float | None = None
    vol120: float | None = None
    mean20: float | None = None
    mean120: float | None = None
    return_count = 0
    alpha20 = 1.0 - math.exp(math.log(0.5) / 20.0)
    alpha120 = 1.0 - math.exp(math.log(0.5) / 120.0)
    for session in sessions:
        close = values.get(session)
        if close is None:
            consecutive = 0
            continue
        log_close = math.log(close)
        previous_log = log_history[-1] if log_history else None
        previous_vol20 = vol20
        previous_vol120 = vol120
        ema20 = close if ema20 is None else (2.0 / 21.0) * close + (19.0 / 21.0) * ema20
        ema60 = close if ema60 is None else (2.0 / 61.0) * close + (59.0 / 61.0) * ema60
        ema20_history.append(ema20)
        history.append(close)
        log_history.append(log_close)
        consecutive += 1
        if previous_log is not None:
            daily_return = log_close - previous_log
            mean20, vol20 = _ewm_update(mean20, vol20, daily_return, alpha20)
            mean120, vol120 = _ewm_update(mean120, vol120, daily_return, alpha120)
            return_count += 1
        if session in wanted:
            metrics = _stock_metrics(
                history=history,
                log_history=log_history,
                close=close,
                ema20=ema20,
                ema60=ema60,
                ema20_history=ema20_history,
                consecutive=consecutive,
                previous_vol20=previous_vol20,
                previous_vol120=previous_vol120,
                return_count=return_count,
            )
            if metrics is not None:
                output[session][instrument_id] = metrics


def _resolve_cross_section(
    pending: Mapping[date, Mapping[str, tuple[float, float, float, float]]],
) -> dict[date, dict[str, StockStructure]]:
    output: dict[date, dict[str, StockStructure]] = {}
    for session, values_by_instrument in pending.items():
        rows = list(values_by_instrument.items())
        if not rows:
            continue
        output[session] = {}
        ordered = sorted(value[2] for _, value in rows)
        for instrument_id, (position_self, momentum_ts, cross_raw, ma_structure) in rows:
            momentum_xs = _percentile_rank(ordered, cross_raw)
            position = 100.0 * (0.45 * position_self + 0.35 * momentum_ts + 0.20 * momentum_xs)
            trend = 100.0 * (0.60 * momentum_ts + 0.25 * momentum_xs + 0.15 * ma_structure)
            p_strong = _sigmoid((trend - 60.0) / 7.0) * _sigmoid((position - 50.0) / 10.0)
            p_low = _sigmoid((40.0 - trend) / 7.0) * _sigmoid((35.0 - position) / 8.0)
            output[session][instrument_id] = StockStructure(
                strong=p_strong >= 0.50,
                low=p_strong < 0.50 and p_low >= 0.55,
            )
    return output


def _stock_metrics(
    *,
    history: deque[float],
    log_history: deque[float],
    close: float,
    ema20: float,
    ema60: float,
    ema20_history: deque[float],
    consecutive: int,
    previous_vol20: float | None,
    previous_vol120: float | None,
    return_count: int,
) -> tuple[float, float, float, float] | None:
    if (
        consecutive < 21
        or len(history) < 120
        or len(log_history) < 61
        or len(ema20_history) < 6
        or previous_vol20 is None
        or previous_vol20 <= 0
        or previous_vol120 is None
        or return_count < 120
    ):
        return None
    ordered = sorted(history)
    position_self = _percentile_rank(ordered, close)
    transformed = {}
    standardized = {}
    logs = list(log_history)
    for horizon in (5, 20, 60):
        z = (logs[-1] - logs[-1 - horizon]) / (previous_vol20 * math.sqrt(horizon))
        z = max(-3.0, min(3.0, z))
        standardized[horizon] = z
        transformed[horizon] = 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))
    momentum_ts = 0.20 * transformed[5] + 0.35 * transformed[20] + 0.45 * transformed[60]
    cross_raw = 0.40 * standardized[20] + 0.60 * standardized[60]
    ma_structure = (
        float(close > ema20) + float(ema20 > ema60) + float(ema20 > list(ema20_history)[-6])
    ) / 3.0
    return position_self, momentum_ts, cross_raw, ma_structure


def _ewm_update(
    mean: float | None,
    variance: float | None,
    value: float,
    alpha: float,
) -> tuple[float, float]:
    if mean is None or variance is None:
        return value, 0.0
    difference = value - mean
    return mean + alpha * difference, (1.0 - alpha) * (variance + alpha * difference * difference)


def _percentile_rank(ordered: Sequence[float], value: float) -> float:
    less = bisect_left(ordered, value)
    equal = bisect_right(ordered, value) - less
    return (less + (equal + 1.0) / 2.0) / len(ordered)


def _sigmoid(value: float) -> float:
    return 1.0 / (1.0 + math.exp(-value))


__all__ = [
    "METHOD_VERSION",
    "IndustryIdentity",
    "MembershipInterval",
    "PriceObservation",
    "build_industry_points",
    "compute_stock_structures",
    "confidence",
    "lifecycle_stage",
]
