"""Immutable realtime aggregates, mutable current pointer, and raw retention ledger."""

from __future__ import annotations

import gzip
import json
import os
import tempfile
import threading
from collections.abc import Sequence
from contextlib import suppress
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from pydantic import BaseModel, TypeAdapter

from ..application.identity import canonical_json, content_hash, file_hash
from ..application.realtime_minutes import aggregate_session_bars
from ..contracts.realtime_projection import (
    RealtimeInstrumentProjection,
    RealtimeMarketProjection,
    RealtimeMinuteBar,
)
from .realtime_aggregation_evidence import expected_minute_keys, verified_observations


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
        rows: list[RealtimeMinuteBar] = []
        if directory.is_dir():
            for path in sorted(directory.glob("*.json.gz")):
                payload = TypeAdapter(tuple[RealtimeMinuteBar, ...]).validate_json(
                    gzip.decompress(path.read_bytes())
                )
                rows.extend(row for row in payload if row.instrument_id == instrument_id)
        parts = self._root / "session-parts" / "1m" / market_date.isoformat()
        if parts.is_dir():
            for path in sorted(parts.glob("*.json.gz")):
                payload = TypeAdapter(tuple[RealtimeMinuteBar, ...]).validate_json(
                    gzip.decompress(path.read_bytes())
                )
                rows.extend(row for row in payload if row.instrument_id == instrument_id)
        try:
            with_current = self.current_instruments()
        except FileNotFoundError:
            with_current = None
        if with_current is not None and with_current.market_date == market_date:
            for row in with_current.open_minutes:
                if row.instrument_id == instrument_id:
                    rows.append(row)
        return aggregate_session_bars(tuple(rows), 1)

    def history_bars(
        self,
        *,
        instrument_id: str,
        frequency: int,
        start_date: date,
        end_date: date,
    ) -> tuple[RealtimeMinuteBar, ...]:
        if end_date < start_date:
            raise ValueError("invalid_realtime_date_window")
        root = self._root / "aggregates" / "1m"
        rows: list[RealtimeMinuteBar] = []
        if root.is_dir():
            for directory in sorted(root.iterdir()):
                try:
                    value = date.fromisoformat(directory.name)
                except ValueError:
                    continue
                if not start_date <= value <= end_date:
                    continue
                rows.extend(self.minute_bars(instrument_id=instrument_id, market_date=value))
        return aggregate_session_bars(tuple(rows), frequency)

    def available_market_dates(self) -> tuple[date, ...]:
        root = self._root / "aggregates" / "1m"
        values = []
        if root.is_dir():
            for directory in root.iterdir():
                try:
                    values.append(date.fromisoformat(directory.name))
                except ValueError:
                    continue
        return tuple(sorted(set(values)))

    def persist_warm_start(
        self,
        *,
        market_date: date,
        request_identity: str,
        raw_payload: object,
        rows: Sequence[RealtimeMinuteBar],
    ) -> tuple[Path, Path | None]:
        digest = request_identity.rsplit(":", 1)[-1]
        raw_path = self._root / "warm-start" / market_date.isoformat() / f"{digest}.raw.json.gz"
        _write_once(raw_path, gzip.compress(canonical_json(raw_payload), mtime=0))
        aggregate = self.append_aggregate(kind="1m", market_date=market_date, rows=rows)
        return raw_path, aggregate

    def persist_session_parts(
        self,
        *,
        market_date: date,
        rows: Sequence[RealtimeMinuteBar],
    ) -> Path | None:
        if not rows:
            return None
        payload = [row.model_dump(mode="json") for row in rows]
        digest = content_hash(payload).rsplit(":", 1)[-1]
        path = self._root / "session-parts" / "1m" / market_date.isoformat() / f"{digest}.json.gz"
        _write_once(path, gzip.compress(canonical_json(payload), mtime=0))
        return path

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
        aggregate_rows: list[RealtimeMinuteBar] = []
        for path in aggregate_paths:
            values = TypeAdapter(tuple[RealtimeMinuteBar, ...]).validate_json(
                gzip.decompress(path.read_bytes())
            )
            aggregate_rows.extend(values)
        if not aggregate_rows:
            raise ValueError("实时会话分钟聚合为空")
        if any(row.session_id != session_id for row in aggregate_rows):
            raise ValueError("实时会话分钟聚合混入其他会话")
        keys = [
            (row.provider, row.session_id, row.instrument_id, row.minute.isoformat())
            for row in aggregate_rows
        ]
        if len(keys) != len(set(keys)):
            raise ValueError("实时会话分钟聚合主键重复")
        if any(not row.is_complete or row.known_gaps for row in aggregate_rows):
            raise ValueError("实时会话分钟聚合含不完整或缺口 Bar")
        aggregate_hashes = {
            str(path.relative_to(self._root)): file_hash(path) for path in aggregate_paths
        }
        directory = self._root / "sessions" / session_id.rsplit(":", 1)[-1]
        microbatch_paths = tuple(sorted((directory / "microbatches").glob("*.json")))
        if not microbatch_paths:
            raise ValueError("实时会话缺少微批证据")
        microbatch_hashes = {
            str(path.relative_to(self._root)): file_hash(path) for path in microbatch_paths
        }
        session_manifest = json.loads((directory / "session.json").read_text(encoding="utf-8"))
        microbatch_values = [
            json.loads(path.read_text(encoding="utf-8")) for path in microbatch_paths
        ]
        microbatch_ids = tuple(str(value["microbatch_id"]) for value in microbatch_values)
        if (
            any(value.get("session_id") != session_id for value in microbatch_values)
            or tuple(session_manifest.get("microbatch_ids", ())) != microbatch_ids
        ):
            raise ValueError("实时会话微批身份与会话清单不一致")
        observations = verified_observations(directory, microbatch_paths)
        expected_keys = expected_minute_keys(
            observations,
            ended_at=datetime.fromisoformat(str(session_manifest["ended_at"])),
        )
        aggregate_keys = {(row.instrument_id, row.minute) for row in aggregate_rows}
        if not expected_keys.issubset(aggregate_keys):
            raise ValueError("实时会话分钟聚合遗漏应聚合的证券或市场分钟")
        payload = {
            "session_id": session_id,
            "verified_at": datetime.now().astimezone().isoformat(),
            "aggregate_kind": "1m",
            "aggregate_hashes": aggregate_hashes,
            "microbatch_hashes": microbatch_hashes,
            "row_count": len(aggregate_rows),
            "primary_key_hash": content_hash(sorted(keys)),
            "expected_coverage_hash": content_hash(
                sorted((instrument, minute.isoformat()) for instrument, minute in expected_keys)
            ),
            "evidence_hash": content_hash(
                {
                    "session_id": session_id,
                    "aggregate_hashes": aggregate_hashes,
                    "microbatch_hashes": microbatch_hashes,
                    "row_count": len(aggregate_rows),
                    "primary_key_hash": content_hash(sorted(keys)),
                    "expected_coverage_hash": content_hash(
                        sorted(
                            (instrument, minute.isoformat()) for instrument, minute in expected_keys
                        )
                    ),
                }
            ),
        }
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
            if not self._aggregation_evidence_valid(value, verified):
                continue
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

    def prune_transient_minute_payloads(
        self,
        *,
        retained_dates: frozenset[date],
    ) -> tuple[Path, ...]:
        removed = []
        for relative in (Path("warm-start"), Path("session-parts/1m")):
            root = self._root / relative
            if not root.is_dir():
                continue
            for directory in root.iterdir():
                try:
                    market_date = date.fromisoformat(directory.name)
                except ValueError:
                    continue
                if market_date in retained_dates:
                    continue
                for path in directory.iterdir():
                    if path.is_file():
                        path.unlink()
                        removed.append(path)
                with suppress(OSError):
                    directory.rmdir()
        return tuple(sorted(removed))

    def _aggregation_evidence_valid(
        self,
        session: dict[str, object],
        path: Path,
    ) -> bool:
        try:
            evidence = json.loads(path.read_text(encoding="utf-8"))
            if evidence.get("session_id") != session.get("session_id"):
                return False
            hashes = evidence["aggregate_hashes"]
            microbatch_hashes = evidence["microbatch_hashes"]
            if (
                not isinstance(hashes, dict)
                or not hashes
                or not isinstance(microbatch_hashes, dict)
                or not microbatch_hashes
            ):
                return False
            if any(
                file_hash(self._root / str(relative)) != expected
                for relative, expected in {**hashes, **microbatch_hashes}.items()
            ):
                return False
            rows = tuple(
                row
                for relative in hashes
                for row in TypeAdapter(tuple[RealtimeMinuteBar, ...]).validate_json(
                    gzip.decompress((self._root / str(relative)).read_bytes())
                )
            )
            keys = sorted(
                (row.provider, row.session_id, row.instrument_id, row.minute.isoformat())
                for row in rows
            )
            if len(keys) != len(set(keys)):
                return False
            if (
                len(rows) != evidence["row_count"]
                or content_hash(keys) != evidence["primary_key_hash"]
                or any(
                    row.session_id != session.get("session_id")
                    or not row.is_complete
                    or row.known_gaps
                    for row in rows
                )
            ):
                return False
            microbatch_ids = tuple(
                str(
                    json.loads((self._root / str(relative)).read_text(encoding="utf-8"))[
                        "microbatch_id"
                    ]
                )
                for relative in sorted(microbatch_hashes)
            )
            session_microbatch_ids = session.get("microbatch_ids")
            if (
                not isinstance(session_microbatch_ids, list | tuple)
                or tuple(str(value) for value in session_microbatch_ids) != microbatch_ids
            ):
                return False
            directory = path.parent
            manifest_paths = tuple(
                self._root / str(relative) for relative in sorted(microbatch_hashes)
            )
            observations = verified_observations(directory, manifest_paths)
            expected_keys = expected_minute_keys(
                observations,
                ended_at=datetime.fromisoformat(str(session["ended_at"])),
            )
            if not expected_keys.issubset({(row.instrument_id, row.minute) for row in rows}):
                return False
            identity = {
                "session_id": evidence["session_id"],
                "aggregate_hashes": hashes,
                "microbatch_hashes": microbatch_hashes,
                "row_count": evidence["row_count"],
                "primary_key_hash": evidence["primary_key_hash"],
                "expected_coverage_hash": evidence["expected_coverage_hash"],
            }
            expected_hash = content_hash(
                sorted((instrument, minute.isoformat()) for instrument, minute in expected_keys)
            )
            return bool(
                evidence.get("expected_coverage_hash") == expected_hash
                and evidence.get("evidence_hash") == content_hash(identity)
            )
        except (FileNotFoundError, KeyError, OSError, TypeError, ValueError):
            return False


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
