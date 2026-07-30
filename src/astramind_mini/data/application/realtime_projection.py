"""Coalesce MiniQMT ticks into a current projection and immutable minute bars."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from ..contracts.realtime import RealtimeQuoteObservation
from ..contracts.realtime_projection import (
    RealtimeBookLevel,
    RealtimeIndexQuote,
    RealtimeIndustryHeat,
    RealtimeInstrumentProjection,
    RealtimeInstrumentQuote,
    RealtimeMarketProjection,
    RealtimeMinuteBar,
)
from .identity import content_hash

BROAD_INDEXES = frozenset(
    {"000001.SH", "399001.SZ", "399006.SZ", "000688.SH", "000300.SH", "000852.SH"}
)
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


class RealtimeQuoteProjector:
    def __init__(
        self,
        *,
        session_id: str,
        industry_membership: dict[str, str] | None = None,
        breadth_universe: frozenset[str] | None = None,
        instrument_names: dict[str, str] | None = None,
        instrument_types: dict[str, str] | None = None,
        price_limits: dict[str, tuple[float, float]] | None = None,
    ) -> None:
        self._session_id = session_id
        self._industry = dict(industry_membership or {})
        self._breadth_universe = breadth_universe
        self._names = dict(instrument_names or {})
        self._types = dict(instrument_types or {})
        self._limits = dict(price_limits or {})
        self._latest: dict[str, RealtimeQuoteObservation] = {}
        self._cumulative: dict[str, tuple[float, float]] = {}
        self._reset_epochs: dict[str, int] = {}
        self._minute_gaps: dict[str, set[str]] = defaultdict(set)
        self._minutes: dict[str, _OpenMinute] = {}
        self._closed: list[RealtimeMinuteBar] = []

    def ingest(self, rows: tuple[RealtimeQuoteObservation, ...]) -> None:
        for row in rows:
            self._latest[row.instrument_id] = row
            self._update_minute(row)

    def project(self, now: datetime) -> RealtimeMarketProjection:
        received = [row.received_at for row in self._latest.values()]
        latest_received = max(received) if received else None
        stale = latest_received is None or now - latest_received > timedelta(seconds=10)
        advancing = declining = unchanged = 0
        industry_changes: dict[str, list[float]] = defaultdict(list)
        indexes = []
        breadth_observed = 0
        for row in self._latest.values():
            change = _change_percent(row)
            include_breadth = (
                self._breadth_universe is None or row.instrument_id in self._breadth_universe
            )
            if change is not None and include_breadth:
                breadth_observed += 1
                if change > 0:
                    advancing += 1
                elif change < 0:
                    declining += 1
                else:
                    unchanged += 1
                industry = self._industry.get(row.instrument_id)
                if industry:
                    industry_changes[industry].append(change)
            if row.instrument_id in BROAD_INDEXES and row.last_price is not None:
                indexes.append(
                    RealtimeIndexQuote(
                        instrument_id=row.instrument_id,
                        last_price=row.last_price,
                        change_percent=change,
                        market_time_ms=row.market_time_ms,
                    )
                )
        industries = tuple(
            RealtimeIndustryHeat(
                industry_code=code,
                change_percent=sum(values) / len(values),
                observed_constituents=len(values),
            )
            for code, values in sorted(industry_changes.items())
        )
        identity = {
            "session_id": self._session_id,
            "as_of": now,
            "quotes": {key: value.raw_content_hash for key, value in sorted(self._latest.items())},
        }
        return RealtimeMarketProjection(
            projection_id=content_hash(identity),
            provider="miniqmt",
            session_id=self._session_id,
            state="stale" if stale else "current",
            as_of=now,
            latest_received_at=latest_received,
            latest_market_time_ms=max(
                (row.market_time_ms or 0 for row in self._latest.values()), default=0
            )
            or None,
            granularity_ms=1000,
            quote_count=len(self._latest),
            breadth_observed=breadth_observed,
            breadth_expected=(
                len(self._breadth_universe) if self._breadth_universe is not None else None
            ),
            breadth_coverage_ratio=(
                breadth_observed / len(self._breadth_universe) if self._breadth_universe else None
            ),
            advancing=advancing,
            declining=declining,
            unchanged=unchanged,
            total_amount=sum(row.amount or 0 for row in self._latest.values()),
            indexes=tuple(sorted(indexes, key=lambda item: item.instrument_id)),
            industries=industries,
            known_gaps=() if self._industry else ("industry_membership_not_loaded",),
        )

    def drain_closed_minutes(self) -> tuple[RealtimeMinuteBar, ...]:
        result = tuple(self._closed)
        self._closed.clear()
        return result

    def instrument_projection(self, now: datetime) -> RealtimeInstrumentProjection:
        latest_received = max(
            (row.received_at for row in self._latest.values()),
            default=None,
        )
        state: Literal["current", "stale", "disconnected"] = (
            "stale"
            if latest_received is None or now - latest_received > timedelta(seconds=10)
            else "current"
        )
        quotes = tuple(
            self._instrument_quote(row)
            for instrument_id, row in sorted(self._latest.items())
            if instrument_id in self._types
        )
        open_minutes = tuple(
            _minute_bar(
                session_id=self._session_id,
                instrument_id=instrument_id,
                current=current,
                is_complete=False,
                known_gaps=tuple(sorted(self._minute_gaps.get(instrument_id, ()))),
                counter_epoch=self._reset_epochs.get(instrument_id, 0),
            )
            for instrument_id, current in sorted(self._minutes.items())
            if instrument_id in self._types
        )
        identity = {
            "session_id": self._session_id,
            "quotes": {key: value.raw_content_hash for key, value in sorted(self._latest.items())},
            "open_minutes": [row.model_dump(mode="json") for row in open_minutes],
        }
        return RealtimeInstrumentProjection(
            projection_id=content_hash(identity),
            provider="miniqmt",
            session_id=self._session_id,
            state=state,
            as_of=now,
            market_date=now.astimezone(SHANGHAI).date(),
            quotes=quotes,
            open_minutes=open_minutes,
            known_gaps=(() if self._limits else ("current_price_limits_not_available",)),
        )

    def close_open_minutes(self) -> tuple[RealtimeMinuteBar, ...]:
        for instrument_id, current in self._minutes.items():
            self._closed.append(
                _minute_bar(
                    session_id=self._session_id,
                    instrument_id=instrument_id,
                    current=current,
                    is_complete=True,
                    known_gaps=tuple(sorted(self._minute_gaps.get(instrument_id, ()))),
                    counter_epoch=self._reset_epochs.get(instrument_id, 0),
                )
            )
        self._minutes.clear()
        return self.drain_closed_minutes()

    def close_completed_minutes(self, now: datetime) -> tuple[RealtimeMinuteBar, ...]:
        completed_before = now.astimezone(SHANGHAI).replace(second=0, microsecond=0)
        completed = tuple(
            instrument_id
            for instrument_id, current in self._minutes.items()
            if current.minute < completed_before
        )
        for instrument_id in completed:
            current = self._minutes.pop(instrument_id)
            self._closed.append(
                _minute_bar(
                    session_id=self._session_id,
                    instrument_id=instrument_id,
                    current=current,
                    is_complete=True,
                    known_gaps=tuple(sorted(self._minute_gaps.pop(instrument_id, ()))),
                    counter_epoch=self._reset_epochs.get(instrument_id, 0),
                )
            )
        return self.drain_closed_minutes()

    def snapshot_open_minutes(self, gap: str) -> tuple[RealtimeMinuteBar, ...]:
        return tuple(
            _minute_bar(
                session_id=self._session_id,
                instrument_id=instrument_id,
                current=current,
                is_complete=False,
                known_gaps=tuple(sorted({gap, *self._minute_gaps.get(instrument_id, ())})),
                counter_epoch=self._reset_epochs.get(instrument_id, 0),
            )
            for instrument_id, current in sorted(self._minutes.items())
        )

    def _update_minute(self, row: RealtimeQuoteObservation) -> None:
        if row.last_price is None:
            return
        prior = self._cumulative.get(row.instrument_id)
        current_volume = row.volume if row.volume is not None else (prior[0] if prior else 0)
        current_amount = row.amount if row.amount is not None else (prior[1] if prior else 0)
        self._cumulative[row.instrument_id] = (current_volume, current_amount)
        if prior is None:
            return
        minute = _market_datetime(row).replace(second=0, microsecond=0)
        current = self._minutes.get(row.instrument_id)
        if current is not None and current.minute != minute:
            self._closed.append(
                _minute_bar(
                    session_id=self._session_id,
                    instrument_id=row.instrument_id,
                    current=current,
                    is_complete=True,
                    known_gaps=tuple(sorted(self._minute_gaps.get(row.instrument_id, ()))),
                    counter_epoch=self._reset_epochs.get(row.instrument_id, 0),
                )
            )
            self._minute_gaps.pop(row.instrument_id, None)
            current = None
        reset = current_volume < prior[0] or current_amount < prior[1]
        if reset:
            self._reset_epochs[row.instrument_id] = self._reset_epochs.get(row.instrument_id, 0) + 1
            self._minute_gaps[row.instrument_id].add("cumulative_counter_reset")
            volume_delta = current_volume
            amount_delta = current_amount
        else:
            volume_delta = current_volume - prior[0]
            amount_delta = current_amount - prior[1]
        if volume_delta == 0 and amount_delta == 0 and not reset:
            return
        if current is None:
            current = _OpenMinute(
                minute=minute,
                open=row.last_price,
                high=row.last_price,
                low=row.last_price,
                close=row.last_price,
            )
            self._minutes[row.instrument_id] = current
        current.high = max(current.high, row.last_price)
        current.low = min(current.low, row.last_price)
        current.close = row.last_price
        current.count += 1
        current.volume += volume_delta
        current.amount += amount_delta
        current.first_observed_at = current.first_observed_at or row.received_at
        current.last_observed_at = row.received_at

    def _instrument_quote(self, row: RealtimeQuoteObservation) -> RealtimeInstrumentQuote:
        limits = self._limits.get(row.instrument_id)
        return RealtimeInstrumentQuote(
            instrument_id=row.instrument_id,
            instrument_name=self._names.get(row.instrument_id),
            instrument_type=self._types.get(row.instrument_id, "other"),  # type: ignore[arg-type]
            industry_code=self._industry.get(row.instrument_id),
            market_time_ms=row.market_time_ms,
            received_at=row.received_at,
            last_price=row.last_price,
            previous_close=row.previous_close,
            change_percent=_change_percent(row),
            open_price=row.open_price,
            high_price=row.high_price,
            low_price=row.low_price,
            volume=row.volume,
            amount=row.amount,
            upper_limit=limits[0] if limits else None,
            lower_limit=limits[1] if limits else None,
            stock_status=row.stock_status,
            status_label=_status_label(row.stock_status),
            bids=_book(row.bid_prices, row.bid_volumes),
            asks=_book(row.ask_prices, row.ask_volumes),
        )


def _change_percent(row: RealtimeQuoteObservation) -> float | None:
    if row.last_price is None or not row.previous_close:
        return None
    return (row.last_price / row.previous_close - 1) * 100


def _market_datetime(row: RealtimeQuoteObservation) -> datetime:
    if row.market_time_ms is not None and row.market_time_ms > 1_000_000_000_000:
        return datetime.fromtimestamp(row.market_time_ms / 1000, tz=SHANGHAI)
    return row.received_at.astimezone(SHANGHAI)


def _minute_bar(
    *,
    session_id: str,
    instrument_id: str,
    current: _OpenMinute,
    is_complete: bool,
    known_gaps: tuple[str, ...],
    counter_epoch: int,
) -> RealtimeMinuteBar:
    identity = content_hash(
        {
            "session_id": session_id,
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
        session_id=session_id,
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
        is_complete=is_complete,
        lifecycle="closed" if is_complete else "forming",
        known_gaps=known_gaps,
        coverage_minutes=1 if is_complete else 0,
        counter_epoch=counter_epoch,
    )


def _book(
    prices: tuple[float, ...],
    volumes: tuple[float, ...],
) -> tuple[RealtimeBookLevel, ...]:
    return tuple(
        RealtimeBookLevel(
            level=index + 1,
            price=prices[index] if index < len(prices) else None,
            volume=volumes[index] if index < len(volumes) else None,
        )
        for index in range(5)
    )


def _status_label(value: int | None) -> str:
    if value is None:
        return "状态未知"
    if value == 0:
        return "正常交易"
    return f"状态代码 {value}"


__all__ = ["BROAD_INDEXES", "RealtimeQuoteProjector"]
