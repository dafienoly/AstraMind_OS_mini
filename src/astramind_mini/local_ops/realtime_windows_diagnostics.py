"""Parse the Windows wrapper's bounded, atomic runtime evidence."""

from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal, cast
from uuid import UUID

WRAPPER_STATUS_FILENAME = "realtime-task-status.json"
WRAPPER_FUTURE_TOLERANCE = timedelta(minutes=5)
WrapperState = Literal[
    "running",
    "completed",
    "wrapper_launch_exception",
    "wsl_native_exit",
]
WrapperStatusReadState = Literal["available", "missing", "unreadable", "invalid"]
_SECRET_PATTERN = re.compile(
    r"""(?ix)
    (?<![a-z0-9_\\/])
    (?P<prefix>["']?(?:token|api[_ -]?key|secret|password|account(?:_id)?)["']?
    \s*(?::|=|\s)\s*)
    (?:"(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*'|[^,;\r\n]*)
    """,
)


@dataclass(frozen=True, slots=True)
class WindowsWrapperDiagnostic:
    schema_version: int
    state: WrapperState
    updated_at: str | None
    updated_at_instant: datetime | None
    attempt_id: str | None
    wsl_executable: str | None
    native_exit_code: int | None
    exception_type: str | None
    exception_message: str | None
    exception_hresult: str | None
    stdout_characters_seen: int
    stderr_characters_seen: int
    stdout_truncated: bool
    stderr_truncated: bool
    log_path: str | None


@dataclass(frozen=True, slots=True)
class WindowsWrapperDiagnosticRead:
    state: WrapperStatusReadState
    diagnostic: WindowsWrapperDiagnostic | None
    error_code: str | None = None


def read_windows_wrapper_diagnostic(
    *,
    environ: Mapping[str, str] | None = None,
    now: datetime | None = None,
) -> WindowsWrapperDiagnostic | None:
    return read_windows_wrapper_diagnostic_result(environ=environ, now=now).diagnostic


def read_windows_wrapper_diagnostic_result(
    *,
    environ: Mapping[str, str] | None = None,
    now: datetime | None = None,
) -> WindowsWrapperDiagnosticRead:
    status_path = _wrapper_status_path(os.environ if environ is None else environ)
    if status_path is None:
        return WindowsWrapperDiagnosticRead("missing", None, "status_path_unavailable")
    try:
        payload = status_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return WindowsWrapperDiagnosticRead("missing", None, "status_file_missing")
    except (OSError, UnicodeError) as error:
        return WindowsWrapperDiagnosticRead("unreadable", None, type(error).__name__)
    try:
        diagnostic = parse_windows_wrapper_diagnostic(payload, now=now)
    except (json.JSONDecodeError, TypeError, ValueError) as error:
        return WindowsWrapperDiagnosticRead("invalid", None, type(error).__name__)
    return WindowsWrapperDiagnosticRead("available", diagnostic)


def parse_windows_wrapper_diagnostic(
    payload: str,
    *,
    now: datetime | None = None,
) -> WindowsWrapperDiagnostic:
    value = json.loads(payload)
    if not isinstance(value, dict):
        raise ValueError("wrapper diagnostic must be an object")
    state = _wrapper_state(value)
    updated_at, updated_at_instant = _updated_at(value.get("updated_at"), now=now)
    return WindowsWrapperDiagnostic(
        schema_version=_integer(value.get("schema_version"), default=1),
        state=state,
        updated_at=updated_at,
        updated_at_instant=updated_at_instant,
        attempt_id=_attempt_id(value.get("attempt_id")),
        wsl_executable=_safe_text(value.get("wsl_executable")),
        native_exit_code=_optional_integer(value.get("native_exit_code", value.get("exit_code"))),
        exception_type=_safe_text(value.get("exception_type")),
        exception_message=_safe_text(
            value.get("exception_message", value.get("last_error")),
            limit=2_048,
        ),
        exception_hresult=_safe_text(value.get("exception_hresult")),
        stdout_characters_seen=_integer(value.get("stdout_characters_seen"), default=0),
        stderr_characters_seen=_integer(value.get("stderr_characters_seen"), default=0),
        stdout_truncated=_boolean(value.get("stdout_truncated"), default=False),
        stderr_truncated=_boolean(value.get("stderr_truncated"), default=False),
        log_path=_safe_text(value.get("log_path")),
    )


def redact_diagnostic_text(value: str, *, limit: int = 4_096) -> str:
    redacted = _SECRET_PATTERN.sub(
        lambda match: f"{match.group('prefix')}<redacted>",
        value,
    )
    return redacted if len(redacted) <= limit else redacted[:limit] + "<truncated>"


def _wrapper_status_path(environ: Mapping[str, str]) -> Path | None:
    local_app_data = environ.get("LOCALAPPDATA")
    if local_app_data and Path(local_app_data).is_absolute():
        return Path(local_app_data) / "AstraMindOSMini" / WRAPPER_STATUS_FILENAME
    user_profile = environ.get("USERPROFILE")
    if user_profile and Path(user_profile).is_absolute():
        return (
            Path(user_profile) / "AppData" / "Local" / "AstraMindOSMini" / WRAPPER_STATUS_FILENAME
        )
    return None


def _wrapper_state(value: dict[str, object]) -> WrapperState:
    state = value.get("state")
    if state in {
        "running",
        "completed",
        "wrapper_launch_exception",
        "wsl_native_exit",
    }:
        return cast(WrapperState, state)
    if state is not None:
        raise ValueError("unknown wrapper diagnostic state")
    exit_code = _optional_integer(value.get("native_exit_code", value.get("exit_code")))
    if exit_code is not None:
        return "completed" if exit_code == 0 else "wsl_native_exit"
    if value.get("last_error") or value.get("exception_type"):
        return "wrapper_launch_exception"
    raise ValueError("legacy wrapper diagnostic has no state evidence")


def _updated_at(
    value: object,
    *,
    now: datetime | None,
) -> tuple[str | None, datetime | None]:
    if value is None:
        return None, None
    if not isinstance(value, str):
        raise TypeError("diagnostic updated_at must be a string")
    try:
        instant = datetime.fromisoformat(value)
    except ValueError as error:
        raise ValueError("diagnostic updated_at must be ISO 8601") from error
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise ValueError("diagnostic updated_at must include a UTC offset")
    current = datetime.now(UTC) if now is None else now
    if current.tzinfo is None or current.utcoffset() is None:
        raise ValueError("diagnostic comparison time must include a UTC offset")
    normalized = instant.astimezone(UTC)
    if normalized > current.astimezone(UTC) + WRAPPER_FUTURE_TOLERANCE:
        raise ValueError("diagnostic updated_at is too far in the future")
    return normalized.isoformat(), normalized


def _attempt_id(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError("diagnostic attempt_id must be a string")
    try:
        return str(UUID(value))
    except ValueError as error:
        raise ValueError("diagnostic attempt_id must be a UUID") from error


def _safe_text(value: object, *, limit: int = 4_096) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError("diagnostic text must be a string")
    return redact_diagnostic_text(value, limit=limit)


def _integer(value: object, *, default: int) -> int:
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError("diagnostic integer must be an integer")
    return value


def _optional_integer(value: object) -> int | None:
    if value is None:
        return None
    return _integer(value, default=0)


def _boolean(value: object, *, default: bool) -> bool:
    if value is None:
        return default
    if not isinstance(value, bool):
        raise TypeError("diagnostic boolean must be a boolean")
    return value


__all__ = [
    "WRAPPER_STATUS_FILENAME",
    "WindowsWrapperDiagnostic",
    "WindowsWrapperDiagnosticRead",
    "parse_windows_wrapper_diagnostic",
    "read_windows_wrapper_diagnostic",
    "read_windows_wrapper_diagnostic_result",
    "redact_diagnostic_text",
]
