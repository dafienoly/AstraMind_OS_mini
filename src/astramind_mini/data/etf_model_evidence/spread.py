"""Prospective ETF L1 spread projection and append-only persistence."""

from __future__ import annotations

import gzip
from collections import defaultdict
from collections.abc import Iterable
from datetime import UTC, date, datetime
from pathlib import Path
from statistics import median
from zoneinfo import ZoneInfo

from astramind_mini.data.application.identity import canonical_json, content_hash
from astramind_mini.data.contracts import RealtimeQuoteObservation

from .contracts import EtfSpreadMinuteObservation

SHANGHAI = ZoneInfo("Asia/Shanghai")
SCHEMA_VERSION = "etf-l1-spread-minute-v1"


class EtfSpreadMinuteProjector:
    def __init__(
        self,
        *,
        feed_session_id: str,
        market_date: date,
        universe: Iterable[str],
    ) -> None:
        self._session = feed_session_id
        self._market_date = market_date
        self._universe = frozenset(universe)
        self._quotes: dict[
            tuple[str, datetime],
            list[tuple[datetime, float | None, str]],
        ] = defaultdict(list)

    def ingest(self, rows: Iterable[RealtimeQuoteObservation]) -> None:
        for row in rows:
            if row.instrument_id not in self._universe:
                continue
            market_time = _market_time(row)
            if market_time.astimezone(SHANGHAI).date() != self._market_date:
                continue
            minute = market_time.astimezone(SHANGHAI).replace(second=0, microsecond=0)
            self._quotes[row.instrument_id, minute].append(
                (market_time, _quoted_spread_bps(row), row.raw_content_hash)
            )

    def drain_closed(self, as_of: datetime) -> tuple[EtfSpreadMinuteObservation, ...]:
        boundary = as_of.astimezone(SHANGHAI).replace(second=0, microsecond=0)
        keys = tuple(key for key in self._quotes if key[1] < boundary)
        return self._drain(keys, as_of)

    def close_open(self, as_of: datetime) -> tuple[EtfSpreadMinuteObservation, ...]:
        return self._drain(tuple(self._quotes), as_of)

    def _drain(
        self,
        keys: tuple[tuple[str, datetime], ...],
        as_of: datetime,
    ) -> tuple[EtfSpreadMinuteObservation, ...]:
        rows: list[EtfSpreadMinuteObservation] = []
        for instrument, minute in sorted(keys):
            samples = self._quotes.pop((instrument, minute))
            valid = [spread for _, spread, _ in samples if spread is not None]
            rows.append(
                EtfSpreadMinuteObservation(
                    provider="miniqmt",
                    feed_session_id=self._session,
                    instrument_id=instrument,
                    market_date=self._market_date,
                    minute=minute,
                    first_market_time=min(item[0] for item in samples),
                    last_market_time=max(item[0] for item in samples),
                    quote_count=len(samples),
                    valid_quote_count=len(valid),
                    quoted_spread_bps_median=median(valid) if valid else None,
                    quoted_spread_bps_p90=_quantile(valid, 0.9) if valid else None,
                    available_at=as_of,
                    source_content_hash=content_hash(
                        {
                            "feed_session_id": self._session,
                            "instrument_id": instrument,
                            "minute": minute,
                            "raw_content_hashes": [item[2] for item in samples],
                        }
                    ),
                    schema_version=SCHEMA_VERSION,
                )
            )
        return tuple(rows)


class EtfSpreadMinuteStore:
    """Stores one immutable multi-ETF payload per closed market minute."""

    def __init__(self, data_root: Path) -> None:
        self._root = data_root / "realtime" / "miniqmt" / "etf-spread"

    def append(
        self,
        rows: tuple[EtfSpreadMinuteObservation, ...],
    ) -> Path | None:
        if not rows:
            return None
        sessions = {row.feed_session_id for row in rows}
        dates = {row.market_date for row in rows}
        minutes = {row.minute for row in rows}
        if len(sessions) != 1 or len(dates) != 1 or len(minutes) != 1:
            raise ValueError("ETF 分钟价差批次必须属于同一会话、日期和分钟")
        payload = [
            row.model_dump(mode="json") for row in sorted(rows, key=lambda item: item.instrument_id)
        ]
        digest = content_hash(payload).removeprefix("sha256:")
        session = next(iter(sessions)).removeprefix("sha256:")
        market_date = next(iter(dates))
        minute = next(iter(minutes)).astimezone(SHANGHAI)
        path = (
            self._root
            / f"market-date={market_date.isoformat()}"
            / f"session={session}"
            / f"{minute:%H%M}-{digest}.json.gz"
        )
        _write_once(path, gzip.compress(canonical_json(payload), mtime=0))
        return path

    def load_dates(
        self,
        market_dates: Iterable[date],
    ) -> tuple[EtfSpreadMinuteObservation, ...]:
        rows: list[EtfSpreadMinuteObservation] = []
        for market_date in sorted(set(market_dates)):
            directory = self._root / f"market-date={market_date.isoformat()}"
            for path in sorted(directory.glob("session=*/*.json.gz")):
                decoded = gzip.decompress(path.read_bytes()).decode("utf-8")
                rows.extend(
                    EtfSpreadMinuteObservation.model_validate_json(item) for item in _items(decoded)
                )
        return tuple(rows)


def _items(payload: str) -> tuple[str, ...]:
    import json

    decoded = json.loads(payload)
    if not isinstance(decoded, list):
        raise ValueError("ETF 分钟价差载荷不是列表")
    return tuple(json.dumps(item, ensure_ascii=False) for item in decoded)


def _market_time(row: RealtimeQuoteObservation) -> datetime:
    if row.market_time_ms is None:
        return row.received_at
    return datetime.fromtimestamp(row.market_time_ms / 1000.0, tz=UTC)


def _quoted_spread_bps(row: RealtimeQuoteObservation) -> float | None:
    if not row.bid_prices or not row.ask_prices:
        return None
    bid, ask = row.bid_prices[0], row.ask_prices[0]
    if bid <= 0 or ask < bid:
        return None
    midpoint = (ask + bid) / 2.0
    return (ask - bid) / midpoint * 10_000.0 if midpoint > 0 else None


def _quantile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * probability
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def _write_once(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as stream:
            stream.write(payload)
    except FileExistsError:
        if path.read_bytes() != payload:
            raise ValueError(f"ETF 分钟价差不可变身份冲突：{path.name}") from None


__all__ = ["EtfSpreadMinuteProjector", "EtfSpreadMinuteStore"]
