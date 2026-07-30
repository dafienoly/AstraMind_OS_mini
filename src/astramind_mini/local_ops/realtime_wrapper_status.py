"""Correlate Windows wrapper evidence with scheduler and Python runtime time."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from astramind_mini.local_ops.realtime_windows_diagnostics import (
    WindowsWrapperDiagnostic,
    WindowsWrapperDiagnosticRead,
)

WRAPPER_FRESHNESS = timedelta(seconds=90)


@dataclass(frozen=True, slots=True)
class WrapperTiming:
    historical: bool
    stale: bool


def correlate_wrapper_timing(
    wrapper: WindowsWrapperDiagnostic | None,
    *,
    runtime_updated_at: datetime | None,
    runtime_healthy: bool,
    now: datetime,
) -> WrapperTiming:
    if wrapper is None or wrapper.updated_at_instant is None:
        return WrapperTiming(historical=False, stale=wrapper is not None)
    wrapper_updated_at = wrapper.updated_at_instant.astimezone(UTC)
    historical = (
        runtime_healthy
        and runtime_updated_at is not None
        and runtime_updated_at.astimezone(UTC) > wrapper_updated_at
    )
    stale = now.astimezone(UTC) - wrapper_updated_at > WRAPPER_FRESHNESS
    return WrapperTiming(historical=historical, stale=stale)


def wrapper_status_lines(
    wrapper_read: WindowsWrapperDiagnosticRead,
    timing: WrapperTiming,
) -> tuple[str, ...]:
    read_state = f"wrapper_status_read_state={wrapper_read.state}"
    wrapper = wrapper_read.diagnostic
    if wrapper is None:
        state = "invalid_diagnostic" if wrapper_read.state == "invalid" else "not_available"
        lines = [read_state, f"wrapper_state={state}"]
        if wrapper_read.error_code is not None:
            lines.append(f"wrapper_status_read_error={wrapper_read.error_code}")
        return tuple(lines)
    lines = [
        read_state,
        f"wrapper_state={wrapper.state}",
        f"wrapper_status_schema_version={wrapper.schema_version}",
    ]
    _append_wrapper_identity(lines, wrapper, timing)
    _append_wrapper_process_evidence(lines, wrapper)
    _append_wrapper_failure(lines, wrapper, historical=timing.historical)
    return tuple(lines)


def resolve_operational_state(
    scheduler_state: str,
    last_result: str | None,
    wrapper_read: WindowsWrapperDiagnosticRead,
    runtime_state: str,
    runtime_read_state: str,
    timing: WrapperTiming,
) -> str:
    if scheduler_state == "not_installed":
        return "not_installed"
    if last_result not in {None, "0", "0x0", "267009", "0x41301"}:
        return "blocked"
    if runtime_read_state in {"missing", "unreadable", "invalid"}:
        return "blocked"
    if runtime_state in {
        "blocked",
        "error",
        "exited",
        "invalid_runtime_status",
        "not_running",
        "stale_process",
        "stopped",
    }:
        return "blocked"
    if scheduler_state == "query_failed":
        return "unknown"
    wrapper = wrapper_read.diagnostic
    if wrapper is None:
        return "unknown"
    if wrapper.state in {"wrapper_launch_exception", "wsl_native_exit"}:
        return runtime_state if timing.historical else "blocked"
    if timing.stale and not timing.historical:
        return "unknown"
    return runtime_state


def _append_wrapper_identity(
    lines: list[str],
    wrapper: WindowsWrapperDiagnostic,
    timing: WrapperTiming,
) -> None:
    if wrapper.attempt_id is not None:
        lines.append(f"wrapper_attempt_id={wrapper.attempt_id}")
    if wrapper.updated_at_instant is None:
        lines.append("wrapper_timestamp_state=legacy_missing")
    else:
        lines.append(
            "wrapper_timestamp_state="
            + ("superseded" if timing.historical else "stale" if timing.stale else "current")
        )
    for name in ("updated_at", "wsl_executable", "exception_type", "exception_hresult"):
        value = getattr(wrapper, name)
        if value is not None:
            lines.append(f"wrapper_{name}={value}")


def _append_wrapper_process_evidence(
    lines: list[str],
    wrapper: WindowsWrapperDiagnostic,
) -> None:
    if wrapper.native_exit_code is not None:
        lines.append(f"wrapper_native_exit_code={wrapper.native_exit_code}")
    if wrapper.exception_message:
        lines.append(f"wrapper_exception_message={wrapper.exception_message}")
    lines.extend(
        (
            f"wrapper_stdout_characters_seen={wrapper.stdout_characters_seen}",
            f"wrapper_stderr_characters_seen={wrapper.stderr_characters_seen}",
            f"wrapper_stdout_truncated={str(wrapper.stdout_truncated).lower()}",
            f"wrapper_stderr_truncated={str(wrapper.stderr_truncated).lower()}",
        )
    )
    if wrapper.log_path:
        lines.append(f"wrapper_log_path={wrapper.log_path}")


def _append_wrapper_failure(
    lines: list[str],
    wrapper: WindowsWrapperDiagnostic,
    *,
    historical: bool,
) -> None:
    if wrapper.state not in {"wrapper_launch_exception", "wsl_native_exit"}:
        return
    lines.append(f"wrapper_historical_failure={str(historical).lower()}")
    if historical:
        lines.append(f"wrapper_historical_failure_origin={wrapper.state}")
        return
    lines.append(f"wrapper_failure_origin={wrapper.state}")
    if wrapper.state == "wrapper_launch_exception":
        lines.extend(("wrapper_recovery_action=核对绝对 wsl.exe、任务身份与异常 HResult 后重试",))
    else:
        lines.append("wrapper_recovery_action=读取 Windows 包装日志与 WSL 运行状态后修复原生退出")


__all__ = [
    "WrapperTiming",
    "correlate_wrapper_timing",
    "resolve_operational_state",
    "wrapper_status_lines",
]
