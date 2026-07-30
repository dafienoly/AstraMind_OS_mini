"""Deterministic reconciliation and Shanghai-session minute aggregation."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timedelta
from itertools import pairwise
from typing import Literal

from ..contracts.realtime_projection import RealtimeMinuteBar
from .identity import content_hash

type RealtimeFrequency = Literal[1, 5, 15, 30, 60, 120]
FREQUENCIES = frozenset({1, 5, 15, 30, 60, 120})
MORNING = (time(9, 30), time(11, 30))
AFTERNOON = (time(13, 0), time(15, 0))


def reconcile_minute_parts(
    rows: tuple[RealtimeMinuteBar, ...],
) -> tuple[RealtimeMinuteBar, ...]:
    grouped: dict[tuple[str, datetime], list[RealtimeMinuteBar]] = defaultdict(list)
    for row in rows:
        grouped[(row.instrument_id, row.minute)].append(row)
    return tuple(
        _reconcile_group(parts) for _, parts in sorted(grouped.items(), key=lambda item: item[0])
    )


def aggregate_session_bars(
    rows: tuple[RealtimeMinuteBar, ...],
    frequency: int,
) -> tuple[RealtimeMinuteBar, ...]:
    if frequency not in FREQUENCIES:
        raise ValueError("unsupported_realtime_frequency")
    reconciled = reconcile_minute_parts(rows)
    if frequency == 1:
        return reconciled
    grouped: dict[tuple[str, datetime], list[RealtimeMinuteBar]] = defaultdict(list)
    for row in reconciled:
        anchor = _bucket_start(row.minute, frequency)
        if anchor is not None:
            grouped[(row.instrument_id, anchor)].append(row)
    return tuple(
        _aggregate_complete(parts, anchor, frequency)
        for (instrument_id, anchor), parts in sorted(grouped.items())
        if instrument_id and _is_complete_bucket(parts, anchor, frequency)
    )


def incomplete_bucket_gaps(
    rows: tuple[RealtimeMinuteBar, ...],
    frequency: int,
) -> tuple[str, ...]:
    if frequency == 1:
        return tuple(
            f"incomplete_minute:{row.instrument_id}:{row.minute.isoformat()}"
            for row in reconcile_minute_parts(rows)
            if not row.is_complete or row.known_gaps
        )
    grouped: dict[tuple[str, datetime], list[RealtimeMinuteBar]] = defaultdict(list)
    for row in reconcile_minute_parts(rows):
        anchor = _bucket_start(row.minute, frequency)
        if anchor is not None:
            grouped[(row.instrument_id, anchor)].append(row)
    return tuple(
        f"incomplete_bucket:{instrument_id}:{anchor.isoformat()}:{frequency}m"
        for (instrument_id, anchor), parts in sorted(grouped.items())
        if not _is_complete_bucket(parts, anchor, frequency)
    )


def _reconcile_group(parts: list[RealtimeMinuteBar]) -> RealtimeMinuteBar:
    unique = {
        row.source_identity or content_hash(row.model_dump(mode="json")): row for row in parts
    }
    warm = sorted(
        (row for row in unique.values() if row.source_kind == "warm_start"),
        key=lambda row: row.source_identity or "",
    )
    l1 = tuple(row for row in unique.values() if row.source_kind == "l1")
    if warm and l1:
        chosen = warm[0]
        conflict = any(_market_values(row) != _market_values(chosen) for row in l1)
        if not conflict:
            return chosen
        return chosen.model_copy(
            update={
                "is_complete": False,
                "lifecycle": "forming",
                "coverage_minutes": 0,
                "known_gaps": ("warm_l1_content_conflict",),
            }
        )
    ordered = sorted(
        unique.values(),
        key=lambda row: (
            row.first_observed_at or row.minute,
            row.last_observed_at or row.minute,
            row.session_id,
        ),
    )
    if len(ordered) == 1:
        return ordered[0]
    overlap = any(
        left.last_observed_at is not None
        and right.first_observed_at is not None
        and left.last_observed_at >= right.first_observed_at
        for left, right in pairwise(ordered)
    )
    gaps = {gap for row in ordered for gap in row.known_gaps}
    if overlap:
        gaps.add("overlapping_session_parts")
    identity = content_hash(
        {"parts": [row.source_identity or row.model_dump(mode="json") for row in ordered]}
    )
    return RealtimeMinuteBar(
        provider="miniqmt",
        session_id=content_hash({"parts": [row.session_id for row in ordered]}),
        instrument_id=ordered[0].instrument_id,
        minute=ordered[0].minute,
        open=ordered[0].open,
        high=max(row.high for row in ordered),
        low=min(row.low for row in ordered),
        close=ordered[-1].close,
        volume=sum(row.volume for row in ordered),
        amount=sum(row.amount for row in ordered),
        observation_count=sum(row.observation_count for row in ordered),
        source_kind="reconciled",
        source_identity=identity,
        first_observed_at=ordered[0].first_observed_at,
        last_observed_at=ordered[-1].last_observed_at,
        is_complete=all(row.is_complete for row in ordered) and not overlap,
        known_gaps=tuple(sorted(gaps)),
        lifecycle="sealed" if not overlap else "forming",
        coverage_minutes=1 if not overlap else 0,
        content_identity=identity,
        counter_epoch=max(row.counter_epoch for row in ordered),
    )


def _bucket_start(value: datetime, frequency: int) -> datetime | None:
    local_time = value.timetz().replace(tzinfo=None)
    for start, end in (MORNING, AFTERNOON):
        if start <= local_time < end:
            anchor = value.replace(
                hour=start.hour,
                minute=start.minute,
                second=0,
                microsecond=0,
            )
            offset = int((value - anchor).total_seconds() // 60)
            return anchor + timedelta(minutes=(offset // frequency) * frequency)
    return None


def _is_complete_bucket(
    parts: list[RealtimeMinuteBar],
    anchor: datetime,
    frequency: int,
) -> bool:
    expected = {anchor + timedelta(minutes=index) for index in range(frequency)}
    actual = {row.minute for row in parts if row.is_complete and not row.known_gaps}
    return actual == expected


def _aggregate_complete(
    rows: list[RealtimeMinuteBar],
    anchor: datetime,
    frequency: int,
) -> RealtimeMinuteBar:
    ordered = sorted(rows, key=lambda row: row.minute)
    identity = content_hash(
        {
            "frequency": frequency,
            "sources": [row.source_identity for row in ordered],
        }
    )
    return RealtimeMinuteBar(
        provider="miniqmt",
        session_id=content_hash({"sources": [row.source_identity for row in ordered]}),
        instrument_id=ordered[0].instrument_id,
        minute=anchor,
        open=ordered[0].open,
        high=max(row.high for row in ordered),
        low=min(row.low for row in ordered),
        close=ordered[-1].close,
        volume=sum(row.volume for row in ordered),
        amount=sum(row.amount for row in ordered),
        observation_count=sum(row.observation_count for row in ordered),
        source_kind="reconciled",
        source_identity=identity,
        first_observed_at=ordered[0].first_observed_at,
        last_observed_at=ordered[-1].last_observed_at,
        is_complete=True,
        lifecycle="sealed",
        coverage_minutes=frequency,
        content_identity=identity,
        counter_epoch=max(row.counter_epoch for row in ordered),
    )


def _market_values(row: RealtimeMinuteBar) -> tuple[float, ...]:
    return (row.open, row.high, row.low, row.close, row.volume, row.amount)


def market_date(value: RealtimeMinuteBar) -> date:
    return value.minute.date()


__all__ = [
    "FREQUENCIES",
    "RealtimeFrequency",
    "aggregate_session_bars",
    "incomplete_bucket_gaps",
    "market_date",
    "reconcile_minute_parts",
]
