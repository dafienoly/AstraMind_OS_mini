"""Prepared lifecycle state for low-latency intraday last-price replacement."""

from __future__ import annotations

import math
from collections import defaultdict, deque
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date

from .lifecycle import (
    PriceObservation,
    StockStructure,
    _resolve_cross_section,
    _stock_metrics,
)


@dataclass(frozen=True, slots=True)
class PreparedStock:
    history: tuple[float, ...]
    log_history: tuple[float, ...]
    ema20: float
    ema60: float
    ema20_history: tuple[float, ...]
    vol20: float
    vol120: float
    return_count: int


def prepare_intraday_stocks(
    observations: Iterable[PriceObservation],
    sessions: Sequence[date],
) -> dict[str, PreparedStock]:
    values: dict[str, dict[date, float]] = defaultdict(dict)
    for row in observations:
        values[row.instrument_id][row.trade_date] = row.close
    return {
        instrument_id: state
        for instrument_id, rows in values.items()
        if (state := _prepare_one(rows, sessions)) is not None
    }


def compute_intraday_structures(
    prepared: Mapping[str, PreparedStock],
    prices: Mapping[str, float],
    market_date: date,
) -> dict[str, StockStructure]:
    pending: dict[str, tuple[float, float, float, float]] = {}
    for instrument_id, state in prepared.items():
        close = prices.get(instrument_id)
        if close is None or close <= 0 or not math.isfinite(close):
            continue
        history = deque(state.history, maxlen=252)
        logs = deque(state.log_history, maxlen=121)
        ema_history = deque(state.ema20_history, maxlen=6)
        ema20 = (2.0 / 21.0) * close + (19.0 / 21.0) * state.ema20
        ema60 = (2.0 / 61.0) * close + (59.0 / 61.0) * state.ema60
        history.append(close)
        logs.append(math.log(close))
        ema_history.append(ema20)
        metrics = _stock_metrics(
            history=history,
            log_history=logs,
            close=close,
            ema20=ema20,
            ema60=ema60,
            ema20_history=ema_history,
            consecutive=len(history),
            previous_vol20=state.vol20,
            previous_vol120=state.vol120,
            return_count=state.return_count + 1,
        )
        if metrics is not None:
            pending[instrument_id] = metrics
    return _resolve_cross_section({market_date: pending}).get(market_date, {})


def _prepare_one(
    values: Mapping[date, float],
    sessions: Sequence[date],
) -> PreparedStock | None:
    history: deque[float] = deque(maxlen=252)
    logs: deque[float] = deque(maxlen=121)
    ema_history: deque[float] = deque(maxlen=6)
    ema20 = ema60 = mean20 = mean120 = vol20 = vol120 = None
    return_count = 0
    alpha20 = 1.0 - math.exp(math.log(0.5) / 20.0)
    alpha120 = 1.0 - math.exp(math.log(0.5) / 120.0)
    for session in sessions:
        close = values.get(session)
        if close is None:
            continue
        previous_log = logs[-1] if logs else None
        ema20 = close if ema20 is None else (2.0 / 21.0) * close + (19.0 / 21.0) * ema20
        ema60 = close if ema60 is None else (2.0 / 61.0) * close + (59.0 / 61.0) * ema60
        history.append(close)
        logs.append(math.log(close))
        ema_history.append(ema20)
        if previous_log is not None:
            daily_return = math.log(close) - previous_log
            mean20, vol20 = _ewm(mean20, vol20, daily_return, alpha20)
            mean120, vol120 = _ewm(mean120, vol120, daily_return, alpha120)
            return_count += 1
    if None in (ema20, ema60, vol20, vol120) or len(history) < 120:
        return None
    assert ema20 is not None and ema60 is not None
    assert vol20 is not None and vol120 is not None
    return PreparedStock(
        history=tuple(history),
        log_history=tuple(logs),
        ema20=float(ema20),
        ema60=float(ema60),
        ema20_history=tuple(ema_history),
        vol20=float(vol20),
        vol120=float(vol120),
        return_count=return_count,
    )


def _ewm(
    mean: float | None,
    variance: float | None,
    value: float,
    alpha: float,
) -> tuple[float, float]:
    if mean is None or variance is None:
        return value, 0.0
    difference = value - mean
    return mean + alpha * difference, (1.0 - alpha) * (variance + alpha * difference * difference)


__all__ = [
    "PreparedStock",
    "compute_intraday_structures",
    "prepare_intraday_stocks",
]
