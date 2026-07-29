"""Immutable realtime aggregates, mutable current pointer, and raw retention ledger."""

from __future__ import annotations

import gzip
import json
import os
import tempfile
import threading
from collections.abc import Sequence
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from pydantic import BaseModel

from ..application.identity import canonical_json, content_hash, file_hash
from ..contracts.realtime_projection import (
    RealtimeInstrumentProjection,
    RealtimeMarketProjection,
    RealtimeMinuteBar,
)


class RealtimeProjectionStore:
    def __init__(self, data_root: Path) -> None:
        self._root = data_root / "realtime" / "miniqmt"
        self._cache_lock = threading.Lock()
        self._market_cache: tuple[tuple[int, int], RealtimeMarketProjection] | None = None
        self._instrument_cache: tuple[tuple[int, int], RealtimeInstrumentProjection] | None = None

    def publish_current(self, projection: RealtimeMarketProjection) -> Path:
        path = self._root / "current" / "market.json"
        _atomic_write(path, canonical_json(projection.model_dump(mode="json")))
        return path

    def current(self) -> RealtimeMarketProjection:
        path = self._root / "current" / "market.json"
        return self._read_cached_market(path)

    def publish_instruments(self, projection: RealtimeInstrumentProjection) -> Path:
        path = self._root / "current" / "instruments.json.gz"
        payload = canonical_json(projection.model_dump(mode="json"))
        _atomic_write(path, gzip.compress(payload, mtime=0))
        return path

    def current_instruments(self) -> RealtimeInstrumentProjection:
        path = self._root / "current" / "instruments.json.gz"
        return self._read_cached_instruments(path)

    def _read_cached_market(self, path: Path) -> RealtimeMarketProjection:
        revision = _revision(path)
        with self._cache_lock:
            if self._market_cache is not None and self._market_cache[0] == revision:
                return self._market_cache[1]
            value = RealtimeMarketProjection.model_validate_json(path.read_text(encoding="utf-8"))
            self._market_cache = (revision, value)
            return value

    def _read_cached_instruments(self, path: Path) -> RealtimeInstrumentProjection:
        revision = _revision(path)
        with self._cache_lock:
            if self._instrument_cache is not None and self._instrument_cache[0] == revision:
                return self._instrument_cache[1]
            value = RealtimeInstrumentProjection.model_validate_json(
                gzip.decompress(path.read_bytes())
            )
            self._instrument_cache = (revision, value)
            return value

    def minute_bars(
        self,
        *,
        instrument_id: str,
        market_date: date,
    ) -> tuple[RealtimeMinuteBar, ...]:
        directory = self._root / "aggregates" / "1m" / market_date.isoformat()
        rows: dict[datetime, RealtimeMinuteBar] = {}
        if directory.is_dir():
            for path in sorted(directory.glob("*.json.gz")):
                payload = json.loads(gzip.decompress(path.read_bytes()))
                for value in payload:
                    if value.get("instrument_id") == instrument_id:
                        row = RealtimeMinuteBar.model_validate(value)
                        rows[row.minute] = row
        with_current = self.current_instruments()
        for row in with_current.open_minutes:
            if row.instrument_id == instrument_id:
                rows[row.minute] = row
        return tuple(rows[key] for key in sorted(rows))

    def append_aggregate(
        self,
        *,
        kind: str,
        market_date: date,
        rows: Sequence[BaseModel],
    ) -> Path | None:
        if not rows:
            return None
        payload = [row.model_dump(mode="json") for row in rows]
        digest = content_hash(payload).rsplit(":", 1)[-1]
        path = self._root / "aggregates" / kind / market_date.isoformat() / f"{digest}.json.gz"
        _write_once(path, gzip.compress(canonical_json(payload), mtime=0))
        return path

    def verify_session_aggregation(
        self,
        *,
        session_id: str,
        aggregate_paths: Sequence[Path],
    ) -> Path:
        if not aggregate_paths or any(not path.is_file() for path in aggregate_paths):
            raise ValueError("实时会话没有完整分钟聚合证据")
        relative_paths = tuple(path.relative_to(self._root) for path in aggregate_paths)
        if any(path.parts[:2] != ("aggregates", "1m") for path in relative_paths):
            raise ValueError("细粒度留存清理只能使用 1 分钟聚合证据")
        payload = {
            "session_id": session_id,
            "verified_at": datetime.now().astimezone().isoformat(),
            "aggregate_kind": "1m",
            "aggregate_hashes": {
                str(path.relative_to(self._root)): file_hash(path) for path in aggregate_paths
            },
        }
        directory = self._root / "sessions" / session_id.rsplit(":", 1)[-1]
        path = directory / "aggregation-verified.json"
        _write_once(path, canonical_json(payload))
        return path

    def prune_raw_payloads(self, *, retained_dates: frozenset[date]) -> tuple[Path, ...]:
        removed = []
        sessions = self._root / "sessions"
        if not sessions.is_dir():
            return ()
        for directory in sessions.iterdir():
            if not directory.is_dir():
                continue
            manifest = directory / "session.json"
            verified = directory / "aggregation-verified.json"
            if not manifest.is_file() or not verified.is_file():
                continue
            value = json.loads(manifest.read_text(encoding="utf-8"))
            market_date = _session_market_date(value)
            if market_date in retained_dates:
                continue
            targets = tuple(
                sorted((*directory.glob("*.raw.json.gz"), *directory.glob("*.normalized.json.gz")))
            )
            if not targets:
                continue
            tombstone = {
                "session_id": value["session_id"],
                "market_date": market_date.isoformat(),
                "removed": [path.name for path in targets],
                "removed_hashes": {path.name: file_hash(path) for path in targets},
                "removed_at": datetime.now().astimezone().isoformat(),
                "reason": "fine_grained_l1_retention_5_trading_days",
            }
            _write_once(directory / "raw-retention-tombstone.json", canonical_json(tombstone))
            for target in targets:
                target.unlink()
                removed.append(target)
        return tuple(removed)


def _session_market_date(value: dict[str, object]) -> date:
    explicit = value.get("market_date")
    if explicit:
        return date.fromisoformat(str(explicit))
    subscribed_at = datetime.fromisoformat(str(value["subscribed_at"]))
    return subscribed_at.astimezone(ZoneInfo("Asia/Shanghai")).date()


def _revision(path: Path) -> tuple[int, int]:
    value = path.stat()
    return value.st_mtime_ns, value.st_size


def _write_once(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as stream:
            stream.write(payload)
    except FileExistsError:
        if path.read_bytes() != payload:
            raise ValueError(f"实时聚合不可变身份冲突：{path.name}") from None


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


__all__ = ["RealtimeProjectionStore"]
