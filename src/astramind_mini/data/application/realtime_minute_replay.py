"""Single deterministic cumulative-tick to minute-bar state machine."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from ..contracts.realtime import RealtimeQuoteObservation
from ..contracts.realtime_projection import RealtimeMinuteBar
from .identity import content_hash

SHANGHAI = ZoneInfo("Asia/Shanghai")


@dataclass(slots=True)
class _OpenMinute:
    minute: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float = 0
    amount: float = 0
    count: int = 0
    first_observed_at: datetime | None = None
    last_observed_at: datetime | None = None


class RealtimeMinuteReplay:
    def __init__(self, session_id: str) -> None:
        self._session_id = session_id
        self._cumulative: dict[str, tuple[float, float]] = {}
        self._reset_epochs: dict[str, int] = {}
        self._gaps: dict[str, set[str]] = defaultdict(set)
        self._open: dict[str, _OpenMinute] = {}
        self._closed: list[RealtimeMinuteBar] = []

    def ingest(self, rows: tuple[RealtimeQuoteObservation, ...]) -> None:
        for row in rows:
            self._ingest_one(row)

    def drain_closed(self) -> tuple[RealtimeMinuteBar, ...]:
        result = tuple(self._closed)
        self._closed.clear()
        return result

    def open_bars(self, gap: str | None = None) -> tuple[RealtimeMinuteBar, ...]:
        return tuple(
            self._bar(
                instrument_id,
                current,
                complete=False,
                extra_gap=gap,
            )
            for instrument_id, current in sorted(self._open.items())
        )

    def close_completed(self, now: datetime) -> tuple[RealtimeMinuteBar, ...]:
        boundary = now.astimezone(SHANGHAI).replace(second=0, microsecond=0)
        for instrument_id in tuple(
            key for key, value in self._open.items() if value.minute < boundary
        ):
            current = self._open.pop(instrument_id)
            self._closed.append(self._bar(instrument_id, current, complete=True))
            self._gaps.pop(instrument_id, None)
        return self.drain_closed()

    def close_all(self) -> tuple[RealtimeMinuteBar, ...]:
        for instrument_id, current in self._open.items():
            self._closed.append(self._bar(instrument_id, current, complete=True))
        self._open.clear()
        return self.drain_closed()

    def _ingest_one(self, row: RealtimeQuoteObservation) -> None:
        if row.last_price is None:
            return
        prior = self._cumulative.get(row.instrument_id)
        volume = row.volume if row.volume is not None else (prior[0] if prior else 0)
        amount = row.amount if row.amount is not None else (prior[1] if prior else 0)
        self._cumulative[row.instrument_id] = (volume, amount)
        if prior is None:
            return
        minute = market_minute(row)
        current = self._open.get(row.instrument_id)
        if current is not None and current.minute != minute:
            self._closed.append(self._bar(row.instrument_id, current, complete=True))
            self._gaps.pop(row.instrument_id, None)
            current = None
        reset = volume < prior[0] or amount < prior[1]
        if reset:
            self._reset_epochs[row.instrument_id] = self._reset_epochs.get(row.instrument_id, 0) + 1
            self._gaps[row.instrument_id].add("cumulative_counter_reset")
        volume_delta = volume if reset else volume - prior[0]
        amount_delta = amount if reset else amount - prior[1]
        if volume_delta == 0 and amount_delta == 0 and not reset:
            return
        current = current or _OpenMinute(
            minute, row.last_price, row.last_price, row.last_price, row.last_price
        )
        self._open[row.instrument_id] = current
        current.high = max(current.high, row.last_price)
        current.low = min(current.low, row.last_price)
        current.close = row.last_price
        current.count += 1
        current.volume += volume_delta
        current.amount += amount_delta
        current.first_observed_at = current.first_observed_at or row.received_at
        current.last_observed_at = row.received_at

    def _bar(
        self,
        instrument_id: str,
        current: _OpenMinute,
        *,
        complete: bool,
        extra_gap: str | None = None,
    ) -> RealtimeMinuteBar:
        gaps = {*self._gaps.get(instrument_id, ())}
        if extra_gap:
            gaps.add(extra_gap)
        identity = content_hash(
            {
                "session_id": self._session_id,
                "instrument_id": instrument_id,
                "minute": current.minute,
                "first_observed_at": current.first_observed_at,
                "last_observed_at": current.last_observed_at,
                "open": current.open,
                "high": current.high,
                "low": current.low,
                "close": current.close,
                "volume": current.volume,
                "amount": current.amount,
            }
        )
        return RealtimeMinuteBar(
            provider="miniqmt",
            session_id=self._session_id,
            instrument_id=instrument_id,
            minute=current.minute,
            open=current.open,
            high=current.high,
            low=current.low,
            close=current.close,
            volume=current.volume,
            amount=current.amount,
            observation_count=current.count,
            source_kind="l1",
            source_identity=identity,
            first_observed_at=current.first_observed_at,
            last_observed_at=current.last_observed_at,
            is_complete=complete,
            known_gaps=tuple(sorted(gaps)),
            lifecycle="closed" if complete else "forming",
            coverage_minutes=1 if complete else 0,
            counter_epoch=self._reset_epochs.get(instrument_id, 0),
        )


def market_minute(row: RealtimeQuoteObservation) -> datetime:
    value = (
        datetime.fromtimestamp(row.market_time_ms / 1000, tz=SHANGHAI)
        if row.market_time_ms is not None and row.market_time_ms > 1_000_000_000_000
        else row.received_at.astimezone(SHANGHAI)
    )
    return value.replace(second=0, microsecond=0)


__all__ = ["RealtimeMinuteReplay", "market_minute"]
