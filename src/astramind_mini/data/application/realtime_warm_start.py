"""Normalize completed same-day MiniQMT 1m history without inventing gaps."""

from __future__ import annotations

from datetime import datetime, time
from math import isfinite
from zoneinfo import ZoneInfo

from ..contracts.realtime_projection import RealtimeMinuteBar
from ..contracts.source import ProviderBatch
from .identity import content_hash

SHANGHAI = ZoneInfo("Asia/Shanghai")


def normalize_warm_start_minutes(
    batch: ProviderBatch,
    *,
    completed_before: datetime,
) -> tuple[RealtimeMinuteBar, ...]:
    rows = []
    for value in batch.rows:
        minute = _minute(value.get("time"))
        if minute is None or minute >= completed_before or not _in_session(minute):
            continue
        instrument_id = str(value.get("instrument_id", ""))
        optional_numbers = tuple(_number(value.get(field)) for field in _fields())
        if not instrument_id or any(item is None for item in optional_numbers):
            continue
        numbers = tuple(item for item in optional_numbers if item is not None)
        open_, high, low, close, volume, amount = numbers
        identity = content_hash(
            {
                "provider": batch.provider_id,
                "instrument_id": instrument_id,
                "minute": minute,
                "values": numbers,
            }
        )
        warm_session_id = content_hash(
            {
                "provider": batch.provider_id,
                "market_date": minute.date(),
                "source_kind": "warm_start",
            }
        )
        rows.append(
            RealtimeMinuteBar(
                provider="miniqmt",
                session_id=warm_session_id,
                instrument_id=instrument_id,
                minute=minute,
                open=open_,
                high=high,
                low=low,
                close=close,
                volume=volume,
                amount=amount,
                observation_count=1,
                source_kind="warm_start",
                source_identity=identity,
                first_observed_at=batch.retrieved_at,
                last_observed_at=batch.retrieved_at,
                retrieved_at=batch.retrieved_at,
                is_complete=True,
                lifecycle="sealed",
                content_identity=identity,
            )
        )
    return tuple(sorted(rows, key=lambda row: (row.instrument_id, row.minute)))


def _minute(value: object) -> datetime | None:
    if not isinstance(value, int | float):
        return None
    return datetime.fromtimestamp(float(value) / 1000, tz=SHANGHAI).replace(second=0, microsecond=0)


def _fields() -> tuple[str, ...]:
    return ("open", "high", "low", "close", "volume", "amount")


def _in_session(value: datetime) -> bool:
    local = value.timetz().replace(tzinfo=None)
    return time(9, 30) <= local < time(11, 30) or time(13) <= local < time(15)


def _number(value: object) -> float | None:
    if not isinstance(value, int | float) or not isfinite(float(value)) or float(value) < 0:
        return None
    return float(value)


__all__ = ["normalize_warm_start_minutes"]
