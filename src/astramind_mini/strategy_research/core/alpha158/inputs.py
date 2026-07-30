"""Validated point-in-time inputs for the local Alpha158 calculator."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal

import numpy as np
import numpy.typing as npt

from ..contracts import CoreInputSnapshot
from ..identity import validate_core_factor_sessions

FloatArray = npt.NDArray[np.float64]
VOLUME_UNIT: Literal["lots_100_shares"] = "lots_100_shares"
_SOURCE_FIELDS = (
    "research_open_index",
    "research_high_index",
    "research_low_index",
    "research_close_index",
    "volume_lots",
    "amount_thousand_cny",
    "raw_close",
)


class Alpha158InputError(ValueError):
    def __init__(self, reason_code: str) -> None:
        self.reason_code = reason_code
        super().__init__(reason_code)


@dataclass(frozen=True)
class Alpha158InstrumentInput:
    instrument_id: str
    market_dates: tuple[date, ...]
    available_at: tuple[datetime, ...]
    research_open_index: FloatArray
    research_high_index: FloatArray
    research_low_index: FloatArray
    research_close_index: FloatArray
    volume_lots: FloatArray
    amount_thousand_cny: FloatArray
    raw_close: FloatArray
    volume_unit: Literal["lots_100_shares"] = VOLUME_UNIT

    def __post_init__(self) -> None:
        if not self.instrument_id:
            raise Alpha158InputError("alpha158_instrument_id_missing")
        if not self.market_dates:
            raise Alpha158InputError("alpha158_common_calendar_empty")
        if (
            len(set(self.market_dates)) != len(self.market_dates)
            or tuple(sorted(self.market_dates)) != self.market_dates
        ):
            raise Alpha158InputError("alpha158_market_dates_not_strictly_increasing")
        if len(self.available_at) != len(self.market_dates):
            raise Alpha158InputError("alpha158_input_shape_mismatch")
        if any(value.tzinfo is None or value.utcoffset() is None for value in self.available_at):
            raise Alpha158InputError("alpha158_available_at_not_timezone_aware")
        if self.volume_unit != VOLUME_UNIT:
            raise Alpha158InputError("alpha158_volume_unit_must_be_lots")
        for field in _SOURCE_FIELDS:
            values = _readonly_float64(getattr(self, field))
            if values.shape != (len(self.market_dates),):
                raise Alpha158InputError("alpha158_input_shape_mismatch")
            if np.isinf(values).any():
                raise Alpha158InputError("alpha158_source_contains_infinity")
            object.__setattr__(self, field, values)
        _validate_source_ranges(self)

    def qlib_inputs(self) -> FloatArray:
        vwap = np.full(len(self.market_dates), np.nan, dtype=np.float64)
        valid = (
            np.isfinite(self.amount_thousand_cny)
            & (self.amount_thousand_cny >= 0.0)
            & np.isfinite(self.volume_lots)
            & (self.volume_lots > 0.0)
            & np.isfinite(self.raw_close)
            & (self.raw_close > 0.0)
            & np.isfinite(self.research_close_index)
        )
        raw_vwap = np.empty(len(self.market_dates), dtype=np.float64)
        raw_vwap.fill(np.nan)
        raw_vwap[valid] = (
            self.amount_thousand_cny[valid] * 1000.0 / (self.volume_lots[valid] * 100.0)
        )
        vwap[valid] = raw_vwap[valid] * self.research_close_index[valid] / self.raw_close[valid]
        matrix = np.column_stack(
            (
                self.research_open_index,
                self.research_high_index,
                self.research_low_index,
                self.research_close_index,
                self.volume_lots,
                vwap,
            )
        )
        return _readonly_float64(matrix)


@dataclass(frozen=True)
class Alpha158BatchInput:
    core_input: CoreInputSnapshot
    instruments: tuple[Alpha158InstrumentInput, ...]

    def __post_init__(self) -> None:
        if not self.instruments:
            raise Alpha158InputError("alpha158_instruments_empty")
        identities = tuple(item.instrument_id for item in self.instruments)
        if len(set(identities)) != len(identities):
            raise Alpha158InputError("alpha158_duplicate_instrument")
        calendar = self.instruments[0].market_dates
        if any(item.market_dates != calendar for item in self.instruments):
            raise Alpha158InputError("alpha158_common_calendar_mismatch")
        self.validated_sessions()
        if any(
            available > self.core_input.cutoff_at
            for item in self.instruments
            for available in item.available_at
        ):
            raise Alpha158InputError("alpha158_input_after_cutoff")

    @property
    def market_dates(self) -> tuple[date, ...]:
        return self.instruments[0].market_dates

    @property
    def instrument_ids(self) -> tuple[str, ...]:
        return tuple(item.instrument_id for item in self.instruments)

    def qlib_input_cube(self) -> FloatArray:
        return _readonly_float64(np.stack(tuple(item.qlib_inputs() for item in self.instruments)))

    def validated_sessions(self) -> tuple[date, ...]:
        try:
            return validate_core_factor_sessions(self.core_input, self.market_dates)
        except ValueError as error:
            raise Alpha158InputError("alpha158_common_calendar_mismatch") from error


def _readonly_float64(values: object) -> FloatArray:
    result = np.array(values, dtype="<f8", order="C", copy=True)
    result.setflags(write=False)
    return result


def _validate_source_ranges(value: Alpha158InstrumentInput) -> None:
    price_fields = (
        value.research_open_index,
        value.research_high_index,
        value.research_low_index,
        value.research_close_index,
    )
    if any(np.any(array[np.isfinite(array)] <= 0.0) for array in price_fields):
        raise Alpha158InputError("alpha158_research_price_not_positive")
    finite_volume = value.volume_lots[np.isfinite(value.volume_lots)]
    finite_amount = value.amount_thousand_cny[np.isfinite(value.amount_thousand_cny)]
    if np.any(finite_volume < 0.0):
        raise Alpha158InputError("alpha158_volume_negative")
    if np.any(finite_amount < 0.0):
        raise Alpha158InputError("alpha158_amount_negative")


__all__ = [
    "VOLUME_UNIT",
    "Alpha158BatchInput",
    "Alpha158InputError",
    "Alpha158InstrumentInput",
    "FloatArray",
]
