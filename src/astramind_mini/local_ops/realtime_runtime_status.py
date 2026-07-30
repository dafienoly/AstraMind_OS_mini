"""Typed, fail-closed reader for the realtime Python status file."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from astramind_mini.local_ops.realtime_service_runtime import RealtimeRuntimeStatus

RuntimeStatusReadState = Literal["available", "missing", "unreadable", "invalid"]


@dataclass(frozen=True, slots=True)
class RuntimeStatusRead:
    state: RuntimeStatusReadState
    status: RealtimeRuntimeStatus | None
    error_code: str | None = None


def read_runtime_status(path: Path) -> RuntimeStatusRead:
    try:
        payload = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return RuntimeStatusRead("missing", None, "status_file_missing")
    except (OSError, UnicodeError) as error:
        return RuntimeStatusRead("unreadable", None, type(error).__name__)
    try:
        status = parse_runtime_status(payload)
    except (json.JSONDecodeError, TypeError, ValueError) as error:
        return RuntimeStatusRead("invalid", None, type(error).__name__)
    return RuntimeStatusRead("available", status)


def parse_runtime_status(payload: str) -> RealtimeRuntimeStatus:
    value = json.loads(payload)
    if not isinstance(value, dict):
        raise ValueError("runtime status must be an object")
    normalized = dict(value)
    failures = normalized.get("retry_failures", ())
    if not isinstance(failures, (list, tuple)) or not all(
        isinstance(item, dict) for item in failures
    ):
        raise TypeError("runtime retry_failures must contain objects")
    normalized["retry_failures"] = tuple(dict(item) for item in failures)
    try:
        status = RealtimeRuntimeStatus(**normalized)
    except TypeError as error:
        raise ValueError("runtime status does not match schema") from error
    _validate_runtime_status(status)
    return status


def _validate_runtime_status(status: RealtimeRuntimeStatus) -> None:
    for name in (
        "state",
        "updated_at",
        "process_state",
        "feed_state",
        "projection_state",
        "completed_day_state",
    ):
        if not isinstance(getattr(status, name), str) or not getattr(status, name):
            raise TypeError(f"runtime {name} must be a non-empty string")
    if isinstance(status.pid, bool) or not isinstance(status.pid, int) or status.pid <= 0:
        raise TypeError("runtime pid must be a positive integer")
    for name in ("messages", "microbatches"):
        value = getattr(status, name)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise TypeError(f"runtime {name} must be a non-negative integer")
    if status.exit_code is not None and (
        isinstance(status.exit_code, bool) or not isinstance(status.exit_code, int)
    ):
        raise TypeError("runtime exit_code must be an integer")
    for name in (
        "market_date",
        "session_id",
        "last_successful_heartbeat_at",
        "last_message_at",
        "last_microbatch_at",
        "last_error",
        "log_path",
        "recovery_action",
    ):
        value = getattr(status, name)
        if value is not None and not isinstance(value, str):
            raise TypeError(f"runtime {name} must be a string")


__all__ = [
    "RuntimeStatusRead",
    "RuntimeStatusReadState",
    "parse_runtime_status",
    "read_runtime_status",
]
