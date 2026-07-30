"""Deterministic Alpha158 fixtures shared by focused and golden tests."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import numpy.typing as npt

from astramind_mini.contracts import DatasetRef, DataSnapshot
from astramind_mini.strategy_research.core import (
    CoreDatasetSlice,
    CoreInputLayer,
    CoreInputSnapshot,
    freeze_core_input_snapshot,
)
from astramind_mini.strategy_research.core.alpha158 import (
    Alpha158BatchInput,
    Alpha158InstrumentInput,
)

FloatArray = npt.NDArray[np.float64]
SHANGHAI = ZoneInfo("Asia/Shanghai")
HASH_A = "sha256:" + "a" * 64
HASH_C = "sha256:" + "c" * 64
INSTRUMENTS = ("600000.SH", "000001.SZ", "300001.SZ")


def common_dates(count: int = 75) -> tuple[date, ...]:
    holidays = {
        date(2025, 10, 1),
        date(2025, 10, 2),
        date(2025, 10, 3),
        date(2025, 10, 6),
        date(2025, 10, 7),
        date(2025, 10, 8),
    }
    result: list[date] = []
    current = date(2025, 9, 1)
    while len(result) < count:
        if current.weekday() < 5 and current not in holidays:
            result.append(current)
        current += timedelta(days=1)
    return tuple(result)


def core_input(dates: tuple[date, ...]) -> CoreInputSnapshot:
    cutoff = datetime.combine(dates[-1], time(18), tzinfo=SHANGHAI)
    data_snapshot = DataSnapshot(
        snapshot_id="snapshot:alpha158-golden",
        as_of=datetime.combine(dates[-1], time(17, 30), tzinfo=SHANGHAI),
        datasets=(
            DatasetRef(
                dataset_name="core_daily",
                dataset_version="alpha158-fixture-v1",
                schema_version="1.0.0",
                content_hash=HASH_A,
            ),
        ),
        known_gaps=(),
        created_at=datetime.combine(dates[-1], time(17, 45), tzinfo=SHANGHAI),
        code_identity="test:alpha158-golden-v1",
    )
    dataset = CoreDatasetSlice(
        dataset_name="core_daily",
        dataset_version="alpha158-fixture-v1",
        schema_version="1.0.0",
        content_hash=HASH_A,
        row_count=len(dates) * len(INSTRUMENTS),
        min_market_date=dates[0],
        max_market_date=dates[-1],
        max_available_at=datetime.combine(dates[-1], time(17), tzinfo=SHANGHAI),
        input_layer=CoreInputLayer.COMPLETED_DAILY,
        sealed=True,
    )
    return freeze_core_input_snapshot(
        data_snapshot=data_snapshot,
        decision_date=dates[-1],
        cutoff_at=cutoff,
        common_calendar_id="fixture-common-calendar-v1",
        common_sessions=dates,
        universe_content_hash=HASH_C,
        datasets=(dataset,),
    )


def synthetic_batch(count: int = 75) -> Alpha158BatchInput:
    dates = common_dates(count)
    return Alpha158BatchInput(
        core_input=core_input(dates),
        instruments=tuple(
            _instrument(identifier, dates, position)
            for position, identifier in enumerate(INSTRUMENTS)
        ),
    )


def batch_from_cube(
    cube: FloatArray,
    *,
    dates: tuple[date, ...],
    instruments: tuple[str, ...] = INSTRUMENTS,
) -> Alpha158BatchInput:
    return Alpha158BatchInput(
        core_input=core_input(dates),
        instruments=tuple(
            _instrument_from_qlib(identifier, dates, cube[index])
            for index, identifier in enumerate(instruments)
        ),
    )


def load_golden_cube(root: Path) -> FloatArray:
    return np.asarray(np.load(root / "inputs.npy", allow_pickle=False), dtype=np.float64)


def delete_date(
    instrument: Alpha158InstrumentInput,
    index: int,
) -> Alpha158InstrumentInput:
    keep = np.arange(len(instrument.market_dates)) != index
    return Alpha158InstrumentInput(
        instrument_id=instrument.instrument_id,
        market_dates=instrument.market_dates[:index] + instrument.market_dates[index + 1 :],
        available_at=instrument.available_at[:index] + instrument.available_at[index + 1 :],
        research_open_index=instrument.research_open_index[keep],
        research_high_index=instrument.research_high_index[keep],
        research_low_index=instrument.research_low_index[keep],
        research_close_index=instrument.research_close_index[keep],
        volume_lots=instrument.volume_lots[keep],
        amount_thousand_cny=instrument.amount_thousand_cny[keep],
        raw_close=instrument.raw_close[keep],
    )


def _instrument(
    identifier: str,
    dates: tuple[date, ...],
    position: int,
) -> Alpha158InstrumentInput:
    length = len(dates)
    index = np.arange(length, dtype=np.float64)
    if position == 0:
        close = 90.0 + index * 0.28 + np.sin(index / 3.0)
    elif position == 1:
        close = 130.0 - index * 0.17 + 2.5 * np.cos(index / 4.0)
        close[25:31] = close[24]
    else:
        close = 70.0 + 1.9e-5 * index + 0.4 * np.sin(index / 5.0)
        close[40:46] = close[39]
    open_ = close * (1.0 + 0.002 * np.sin(index + position))
    high = np.maximum(open_, close) + 0.3 + (index % 4) * 0.02
    low = np.minimum(open_, close) - 0.25 - (index % 3) * 0.02
    high[18] = low[18] = open_[18] = close[18]
    high[33] = high[32]
    low[34] = low[33]
    volume = 1200.0 + position * 200.0 + (index % 9) * 75.0
    volume[[7, 8, 29]] = 0.0
    raw_close = close / (1.0 + position * 0.1)
    raw_vwap = raw_close * (1.0 + 0.001 * np.cos(index / 2.0))
    amount = raw_vwap * volume * 100.0 / 1000.0
    missing = 12 + position * 9
    for values in (open_, high, low, close, volume, amount, raw_close):
        values[missing] = np.nan
    available = tuple(datetime.combine(day, time(17), tzinfo=SHANGHAI) for day in dates)
    return Alpha158InstrumentInput(
        instrument_id=identifier,
        market_dates=dates,
        available_at=available,
        research_open_index=open_,
        research_high_index=high,
        research_low_index=low,
        research_close_index=close,
        volume_lots=volume,
        amount_thousand_cny=amount,
        raw_close=raw_close,
    )


def _instrument_from_qlib(
    identifier: str,
    dates: tuple[date, ...],
    values: FloatArray,
) -> Alpha158InstrumentInput:
    open_, high, low, close, volume, vwap = (
        np.array(values[:, index], dtype=np.float64, copy=True) for index in range(6)
    )
    raw_close = close.copy()
    amount = np.full(len(dates), np.nan, dtype=np.float64)
    valid = np.isfinite(vwap) & np.isfinite(volume) & (volume > 0.0)
    amount[valid] = vwap[valid] * volume[valid] * 100.0 / 1000.0
    available = tuple(datetime.combine(day, time(17), tzinfo=SHANGHAI) for day in dates)
    return Alpha158InstrumentInput(
        instrument_id=identifier,
        market_dates=dates,
        available_at=available,
        research_open_index=open_,
        research_high_index=high,
        research_low_index=low,
        research_close_index=close,
        volume_lots=volume,
        amount_thousand_cny=amount,
        raw_close=raw_close,
    )


__all__ = [
    "INSTRUMENTS",
    "SHANGHAI",
    "batch_from_cube",
    "common_dates",
    "core_input",
    "delete_date",
    "load_golden_cube",
    "synthetic_batch",
]
