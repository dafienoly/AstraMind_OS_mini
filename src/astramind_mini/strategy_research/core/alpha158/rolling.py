"""NumPy-only rolling operators with the frozen Qlib Alpha158 semantics."""

from __future__ import annotations

from collections.abc import Callable

import numpy as np

from .inputs import FloatArray

WindowFunction = Callable[[FloatArray], float]


def ref(values: FloatArray, periods: int) -> FloatArray:
    result = _empty(values)
    if periods == 0:
        result[:] = values
    elif periods < len(values):
        result[periods:] = values[:-periods]
    return result


def rolling_mean(values: FloatArray, window: int) -> FloatArray:
    return _rolling(values, window, _nan_mean)


def rolling_sum(values: FloatArray, window: int) -> FloatArray:
    return _rolling(values, window, _nan_sum)


def rolling_std(values: FloatArray, window: int) -> FloatArray:
    return _rolling(values, window, _sample_std)


def rolling_max(values: FloatArray, window: int) -> FloatArray:
    return _rolling(values, window, _nan_max)


def rolling_min(values: FloatArray, window: int) -> FloatArray:
    return _rolling(values, window, _nan_min)


def rolling_quantile(values: FloatArray, window: int, quantile: float) -> FloatArray:
    return _rolling(
        values,
        window,
        lambda item: _linear_quantile(item, quantile),
    )


def rolling_rank(values: FloatArray, window: int) -> FloatArray:
    return _rolling(values, window, _rank_of_current)


def rolling_idxmax(values: FloatArray, window: int) -> FloatArray:
    return _rolling(values, window, _idxmax)


def rolling_idxmin(values: FloatArray, window: int) -> FloatArray:
    return _rolling(values, window, _idxmin)


def rolling_corr(left: FloatArray, right: FloatArray, window: int) -> FloatArray:
    if left.shape != right.shape:
        raise ValueError("rolling correlation inputs must have equal shape")
    paired_finite = np.isfinite(left) & np.isfinite(right)
    x = np.where(paired_finite, left, np.nan)
    y = np.where(paired_finite, right, np.nan)
    mean_xy = _pandas_rolling_mean(x * y, window)
    mean_x = _pandas_rolling_mean(x, window)
    mean_y = _pandas_rolling_mean(y, window)
    x_var = _pandas_rolling_var(x, window)
    y_var = _pandas_rolling_var(y, window)
    paired = paired_finite.astype(np.float64)
    count = rolling_sum(paired, window)
    with np.errstate(all="ignore"):
        result = (mean_xy - mean_x * mean_y) * (count / (count - 1.0)) / np.sqrt(x_var * y_var)
    result[
        np.isclose(rolling_std(left, window), 0.0, atol=2e-5)
        | np.isclose(rolling_std(right, window), 0.0, atol=2e-5)
    ] = np.nan
    return result


class _RollingMeanState:
    def __init__(self) -> None:
        self.count = 0
        self.total = 0.0
        self.add_compensation = 0.0
        self.remove_compensation = 0.0
        self.consecutive_same = 0
        self.previous = np.nan

    def add(self, value: float) -> None:
        if np.isnan(value):
            return
        self.count += 1
        adjusted = value - self.add_compensation
        updated = self.total + adjusted
        self.add_compensation = updated - self.total - adjusted
        self.total = updated
        self.consecutive_same = self.consecutive_same + 1 if value == self.previous else 1
        self.previous = value

    def remove(self, value: float) -> None:
        if np.isnan(value):
            return
        self.count -= 1
        adjusted = -value - self.remove_compensation
        updated = self.total + adjusted
        self.remove_compensation = updated - self.total - adjusted
        self.total = updated

    def value(self) -> float:
        if self.count == 0:
            return float("nan")
        if self.consecutive_same >= self.count:
            return float(self.previous)
        result = self.total / self.count
        return 0.0 if self.total >= 0.0 and result < 0.0 else result


class _RollingVarState:
    def __init__(self) -> None:
        self.count = 0.0
        self.mean = 0.0
        self.sum_squared_deviations = 0.0
        self.add_compensation = 0.0
        self.remove_compensation = 0.0
        self.consecutive_same = 0
        self.previous = np.nan

    def add(self, value: float) -> None:
        if np.isnan(value):
            return
        self.count += 1.0
        self.consecutive_same = self.consecutive_same + 1 if value == self.previous else 1
        self.previous = value
        previous_mean = self.mean - self.add_compensation
        adjusted = value - self.add_compensation
        delta = adjusted - self.mean
        self.add_compensation = delta + self.mean - adjusted
        self.mean += delta / self.count
        self.sum_squared_deviations += (value - previous_mean) * (value - self.mean)

    def remove(self, value: float) -> None:
        if np.isnan(value):
            return
        self.count -= 1.0
        if self.count:
            previous_mean = self.mean - self.remove_compensation
            adjusted = value - self.remove_compensation
            delta = adjusted - self.mean
            self.remove_compensation = delta + self.mean - adjusted
            self.mean -= delta / self.count
            self.sum_squared_deviations -= (value - previous_mean) * (value - self.mean)
        else:
            self.mean = 0.0
            self.sum_squared_deviations = 0.0

    def value(self) -> float:
        if self.count <= 1.0:
            return float("nan")
        if self.consecutive_same >= self.count:
            return 0.0
        return self.sum_squared_deviations / (self.count - 1.0)


def _pandas_rolling_mean(values: FloatArray, window: int) -> FloatArray:
    state = _RollingMeanState()
    result = _empty(values)
    for index, value in enumerate(values):
        if index >= window:
            state.remove(float(values[index - window]))
        state.add(float(value))
        result[index] = state.value()
    return result


def _pandas_rolling_var(values: FloatArray, window: int) -> FloatArray:
    state = _RollingVarState()
    result = _empty(values)
    for index, value in enumerate(values):
        if index >= window:
            state.remove(float(values[index - window]))
        state.add(float(value))
        result[index] = state.value()
    return result


def _rolling(values: FloatArray, window: int, function: WindowFunction) -> FloatArray:
    if window <= 0:
        raise ValueError("rolling window must be positive")
    result = _empty(values)
    for end in range(len(values)):
        start = max(0, end - window + 1)
        result[end] = function(values[start : end + 1])
    return result


def _valid(values: FloatArray) -> FloatArray:
    # Pandas rolling sanitizes both signed infinities and NaN before ordinary
    # reductions. IdxMax/IdxMin intentionally bypass this helper because Qlib
    # applies raw NumPy argmax/argmin to those windows.
    return values[np.isfinite(values)]


def _nan_mean(values: FloatArray) -> float:
    valid = _valid(values)
    return float(np.mean(valid)) if len(valid) else float("nan")


def _nan_sum(values: FloatArray) -> float:
    valid = _valid(values)
    return float(np.sum(valid)) if len(valid) else float("nan")


def _sample_std(values: FloatArray) -> float:
    valid = _valid(values)
    return float(np.std(valid, ddof=1)) if len(valid) >= 2 else float("nan")


def _nan_max(values: FloatArray) -> float:
    valid = _valid(values)
    return float(np.max(valid)) if len(valid) else float("nan")


def _nan_min(values: FloatArray) -> float:
    valid = _valid(values)
    return float(np.min(valid)) if len(valid) else float("nan")


def _linear_quantile(values: FloatArray, quantile: float) -> float:
    valid = _valid(values)
    return float(np.quantile(valid, quantile, method="linear")) if len(valid) else float("nan")


def _rank_of_current(values: FloatArray) -> float:
    current = values[-1]
    if not np.isfinite(current):
        return float("nan")
    valid = _valid(values)
    below = np.count_nonzero(valid < current)
    equal = np.count_nonzero(valid == current)
    average_rank = below + (equal + 1.0) / 2.0
    return float(average_rank / len(valid))


def _idxmax(values: FloatArray) -> float:
    return float(np.argmax(values) + 1)


def _idxmin(values: FloatArray) -> float:
    return float(np.argmin(values) + 1)


def _empty(values: FloatArray) -> FloatArray:
    result = np.empty_like(values, dtype=np.float64)
    result.fill(np.nan)
    return result


__all__ = [
    "ref",
    "rolling_corr",
    "rolling_idxmax",
    "rolling_idxmin",
    "rolling_max",
    "rolling_mean",
    "rolling_min",
    "rolling_quantile",
    "rolling_rank",
    "rolling_std",
    "rolling_sum",
]
