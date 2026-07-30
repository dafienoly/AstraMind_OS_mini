"""Literal cross-row state machines from Qlib rolling.pyx."""

from __future__ import annotations

from collections import deque

import numpy as np

from .inputs import FloatArray


class _SlopeState:
    def __init__(self, window: int) -> None:
        self.window = window
        self.barv = deque(np.float64(np.nan) for _ in range(window))
        self.na_count = window
        self.i_sum = np.float64(0.0)
        self.x_sum = np.float64(0.0)
        self.x2_sum = np.float64(0.0)
        self.y_sum = np.float64(0.0)
        self.xy_sum = np.float64(0.0)

    def advance(self, value: np.float64) -> int:
        self.barv.append(value)
        self.xy_sum = self.xy_sum - self.y_sum
        self.x2_sum = self.x2_sum + self.i_sum - 2 * self.x_sum
        self.x_sum = self.x_sum - self.i_sum
        old = self.barv.popleft()
        if not np.isnan(old):
            self.i_sum -= 1
            self.y_sum -= old
        else:
            self.na_count -= 1
        if np.isnan(value):
            self.na_count += 1
        else:
            self.i_sum += 1
            self.x_sum += self.window
            self.x2_sum += self.window * self.window
            self.y_sum += value
            self.xy_sum += self.window * value
        return self.window - self.na_count

    def slope(self, count: int) -> np.float64:
        numerator = count * self.xy_sum - self.x_sum * self.y_sum
        denominator = count * self.x2_sum - self.x_sum * self.x_sum
        return np.float64(np.divide(numerator, denominator))


class _RsquareState(_SlopeState):
    def __init__(self, window: int) -> None:
        super().__init__(window)
        self.y2_sum = np.float64(0.0)

    def update(self, value: np.float64) -> np.float64:
        self.barv.append(value)
        self.xy_sum = self.xy_sum - self.y_sum
        self.x2_sum = self.x2_sum + self.i_sum - 2 * self.x_sum
        self.x_sum = self.x_sum - self.i_sum
        old = self.barv.popleft()
        if not np.isnan(old):
            self.i_sum -= 1
            self.y_sum -= old
            self.y2_sum -= old * old
        else:
            self.na_count -= 1
        if np.isnan(value):
            self.na_count += 1
        else:
            self.i_sum += 1
            self.x_sum += self.window
            self.x2_sum += self.window * self.window
            self.y_sum += value
            self.y2_sum += value * value
            self.xy_sum += self.window * value
        count = self.window - self.na_count
        numerator = count * self.xy_sum - self.x_sum * self.y_sum
        x_term = count * self.x2_sum - self.x_sum * self.x_sum
        y_term = count * self.y2_sum - self.y_sum * self.y_sum
        correlation = np.divide(numerator, np.sqrt(x_term * y_term))
        return np.float64(correlation * correlation)


def rolling_slope(values: FloatArray, window: int) -> FloatArray:
    state = _SlopeState(window)
    result = np.empty_like(values, dtype=np.float64)
    with np.errstate(all="ignore"):
        for index, value in enumerate(values):
            count = state.advance(np.float64(value))
            result[index] = state.slope(count)
    return result


def rolling_rsquare(values: FloatArray, window: int) -> FloatArray:
    state = _RsquareState(window)
    result = np.empty_like(values, dtype=np.float64)
    with np.errstate(all="ignore"):
        for index, value in enumerate(values):
            result[index] = state.update(np.float64(value))
    return result


def rolling_residual(values: FloatArray, window: int) -> FloatArray:
    state = _SlopeState(window)
    result = np.empty_like(values, dtype=np.float64)
    with np.errstate(all="ignore"):
        for index, value in enumerate(values):
            current = np.float64(value)
            count = state.advance(current)
            slope = state.slope(count)
            x_mean = np.divide(state.x_sum, count)
            y_mean = np.divide(state.y_sum, count)
            intercept = y_mean - slope * x_mean
            result[index] = current - (slope * window + intercept)
    return result


__all__ = ["rolling_residual", "rolling_rsquare", "rolling_slope"]
