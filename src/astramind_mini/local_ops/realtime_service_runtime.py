"""Runtime guardrails and observable state for the read-only realtime service."""

from __future__ import annotations

import fcntl
import json
import os
import tempfile
from dataclasses import asdict, dataclass, field
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
    process_state: str = "running"
    feed_state: str = "not_started"
    projection_state: str = "unknown"
    completed_day_state: str = "unknown"
    market_date: str | None = None
    session_id: str | None = None
    messages: int = 0
    microbatches: int = 0
    last_successful_heartbeat_at: str | None = None
    last_message_at: str | None = None
    last_microbatch_at: str | None = None
    exit_code: int | None = None
    last_error: str | None = None
    retry_failures: tuple[dict[str, object], ...] = field(default_factory=tuple)
    log_path: str | None = None
    recovery_action: str | None = None


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
        process_state: str = "running",
        feed_state: str = "not_started",
        projection_state: str = "unknown",
        completed_day_state: str | None = None,
        last_message_at: datetime | None = None,
        last_microbatch_at: datetime | None = None,
        exit_code: int | None = None,
        last_error: str | None = None,
        retry_failures: tuple[dict[str, object], ...] = (),
        recovery_action: str | None = None,
        successful_heartbeat: bool = False,
    ) -> None:
        now = datetime.now(UTC)
        previous = self.read()
        last_heartbeat = (
            now.isoformat()
            if successful_heartbeat
            else previous.last_successful_heartbeat_at
            if previous is not None
            else None
        )
        status = RealtimeRuntimeStatus(
            state=state,
            updated_at=now.isoformat(),
            pid=os.getpid(),
            process_state=process_state,
            feed_state=feed_state,
            projection_state=projection_state,
            completed_day_state=(
                completed_day_state
                if completed_day_state is not None
                else previous.completed_day_state
                if previous is not None
                else "unknown"
            ),
            market_date=market_date.isoformat() if market_date else None,
            session_id=session_id,
            messages=messages,
            microbatches=microbatches,
            last_successful_heartbeat_at=last_heartbeat,
            last_message_at=(
                last_message_at.isoformat()
                if last_message_at
                else previous.last_message_at
                if previous
                else None
            ),
            last_microbatch_at=(
                last_microbatch_at.isoformat()
                if last_microbatch_at
                else previous.last_microbatch_at
                if previous
                else None
            ),
            exit_code=exit_code,
            last_error=last_error,
            retry_failures=retry_failures[-4:],
            log_path=str(self.path.with_name("service.log")),
            recovery_action=recovery_action,
        )
        _atomic_write(self.path, json.dumps(asdict(status), ensure_ascii=False).encode())

    def read(self) -> RealtimeRuntimeStatus | None:
        if not self.path.is_file():
            return None
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        payload["retry_failures"] = tuple(payload.get("retry_failures", ()))
        return RealtimeRuntimeStatus(**payload)

    def publish_connecting(self, market_date: date, session_id: str) -> None:
        previous = self.read()
        self.publish(
            "connecting",
            market_date=market_date,
            session_id=session_id,
            feed_state="connecting",
            last_error=previous.last_error if previous else None,
            retry_failures=previous.retry_failures if previous else (),
            recovery_action=previous.recovery_action if previous else None,
            successful_heartbeat=False,
        )


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


def realtime_session_state(now: datetime) -> str:
    local = now.astimezone(SHANGHAI).time().replace(tzinfo=None)
    if local < time(9, 30):
        return "preopen"
    if time(11, 30) <= local < time(13):
        return "lunch_break"
    if local >= time(15):
        return "sealing"
    return "capturing"


def realtime_ingestion_open(now: datetime) -> bool:
    local = now.astimezone(SHANGHAI).time().replace(tzinfo=None)
    return time(8, 55) <= local < time(15)


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
    "realtime_ingestion_open",
    "realtime_session_state",
    "retained_open_dates",
]
