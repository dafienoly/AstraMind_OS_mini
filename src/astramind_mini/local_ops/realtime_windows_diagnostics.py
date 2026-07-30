"""Parse the Windows wrapper's bounded, atomic runtime evidence."""

from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

WRAPPER_STATUS_FILENAME = "realtime-task-status.json"
WrapperState = Literal[
    "running",
    "completed",
    "wrapper_launch_exception",
    "wsl_native_exit",
]
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


def read_windows_wrapper_diagnostic(
    *,
    environ: Mapping[str, str] | None = None,
) -> WindowsWrapperDiagnostic | None:
    status_path = _wrapper_status_path(os.environ if environ is None else environ)
    if status_path is None or not status_path.is_file():
        return None
    try:
        return parse_windows_wrapper_diagnostic(status_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError):
        return None


def parse_windows_wrapper_diagnostic(payload: str) -> WindowsWrapperDiagnostic:
    value = json.loads(payload)
    if not isinstance(value, dict):
        raise ValueError("wrapper diagnostic must be an object")
    state = _wrapper_state(value)
    return WindowsWrapperDiagnostic(
        schema_version=_integer(value.get("schema_version"), default=1),
        state=state,
        updated_at=_safe_text(value.get("updated_at")),
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
    "parse_windows_wrapper_diagnostic",
    "read_windows_wrapper_diagnostic",
    "redact_diagnostic_text",
]
