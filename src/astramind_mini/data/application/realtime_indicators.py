"""Closed-bar MA and MACD calculations for the realtime history API."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from ..contracts.realtime_projection import RealtimeMinuteBar


class RealtimeIndicatorPoint(BaseModel):
    minute: datetime
    ma5: float | None = None
    ma10: float | None = None
    ma30: float | None = None
    ma60: float | None = None
    macd: float | None = None
    signal: float | None = None
    histogram: float | None = None


def compute_realtime_indicators(
    bars: tuple[RealtimeMinuteBar, ...],
) -> tuple[tuple[RealtimeIndicatorPoint, ...], str]:
    closed = tuple(row for row in bars if row.is_complete and not row.known_gaps)
    if len(closed) < 60:
        return (), "insufficient_seed"
    closes = [row.close for row in closed]
    ema12 = _ema(closes, 12)
    ema26 = _ema(closes, 26)
    dif = [left - right for left, right in zip(ema12, ema26, strict=True)]
    signal = _ema(dif, 9)
    points = tuple(
        RealtimeIndicatorPoint(
            minute=row.minute,
            ma5=_mean(closes, index, 5),
            ma10=_mean(closes, index, 10),
            ma30=_mean(closes, index, 30),
            ma60=_mean(closes, index, 60),
            macd=dif[index] if index >= 25 else None,
            signal=signal[index] if index >= 33 else None,
            histogram=((dif[index] - signal[index]) * 2 if index >= 33 else None),
        )
        for index, row in enumerate(closed)
    )
    return points, "ready"


def _mean(values: list[float], index: int, window: int) -> float | None:
    if index + 1 < window:
        return None
    return sum(values[index + 1 - window : index + 1]) / window


def _ema(values: list[float], window: int) -> list[float]:
    alpha = 2 / (window + 1)
    result = [values[0]]
    for value in values[1:]:
        result.append(alpha * value + (1 - alpha) * result[-1])
    return result


__all__ = ["RealtimeIndicatorPoint", "compute_realtime_indicators"]
