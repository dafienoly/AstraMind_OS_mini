"""Runtime guardrails and observable state for the read-only realtime service."""

from __future__ import annotations

import fcntl
import json
import os
import tempfile
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, time
from pathlib import Path
from typing import TextIO
from zoneinfo import ZoneInfo

SHANGHAI = ZoneInfo("Asia/Shanghai")
CAPTURE_START = time(8, 55)
CAPTURE_END = time(16, 5)


@dataclass(frozen=True, slots=True)
class RealtimeRuntimeStatus:
    state: str
    updated_at: str
    pid: int
    market_date: str | None = None
    session_id: str | None = None
    messages: int = 0
    microbatches: int = 0
    last_error: str | None = None


class RealtimeServiceLock:
    def __init__(self, control_root: Path) -> None:
        self._path = control_root / "service.lock"
        self._stream: TextIO | None = None

    def __enter__(self) -> RealtimeServiceLock:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        stream = self._path.open("a+", encoding="utf-8")
        try:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            stream.close()
            raise RuntimeError("realtime_market_service_already_running") from None
        stream.seek(0)
        stream.truncate()
        stream.write(str(os.getpid()))
        stream.flush()
        self._stream = stream
        return self

    def __exit__(self, *_: object) -> None:
        stream = self._stream
        if stream is not None:
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
            stream.close()
        self._path.unlink(missing_ok=True)


class RealtimeStatusStore:
    def __init__(self, control_root: Path) -> None:
        self.path = control_root / "status.json"

    def publish(
        self,
        state: str,
        *,
        market_date: date | None = None,
        session_id: str | None = None,
        messages: int = 0,
        microbatches: int = 0,
        last_error: str | None = None,
    ) -> None:
        status = RealtimeRuntimeStatus(
            state=state,
            updated_at=datetime.now(UTC).isoformat(),
            pid=os.getpid(),
            market_date=market_date.isoformat() if market_date else None,
            session_id=session_id,
            messages=messages,
            microbatches=microbatches,
            last_error=last_error,
        )
        _atomic_write(self.path, json.dumps(asdict(status), ensure_ascii=False).encode())

    def read(self) -> RealtimeRuntimeStatus | None:
        if not self.path.is_file():
            return None
        return RealtimeRuntimeStatus(**json.loads(self.path.read_text(encoding="utf-8")))


def active_capture_deadline(
    now: datetime,
    open_dates: tuple[date, ...],
) -> tuple[date, datetime] | None:
    local = now.astimezone(SHANGHAI)
    if local.date() not in frozenset(open_dates):
        return None
    if not (CAPTURE_START <= local.time().replace(tzinfo=None) < CAPTURE_END):
        return None
    deadline = datetime.combine(local.date(), CAPTURE_END, tzinfo=SHANGHAI)
    return local.date(), deadline


def retained_open_dates(open_dates: tuple[date, ...], today: date) -> frozenset[date]:
    eligible = tuple(value for value in open_dates if value <= today)
    return frozenset(eligible[-5:])


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


__all__ = [
    "CAPTURE_END",
    "CAPTURE_START",
    "SHANGHAI",
    "RealtimeRuntimeStatus",
    "RealtimeServiceLock",
    "RealtimeStatusStore",
    "active_capture_deadline",
    "retained_open_dates",
]
