"""Fail-closed parsing and health evidence for the realtime Python runtime."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from astramind_mini.local_ops.realtime_runtime_status import (
    RuntimeStatusRead,
    RuntimeStatusReadState,
)
from astramind_mini.local_ops.realtime_service_runtime import RealtimeRuntimeStatus
from astramind_mini.local_ops.realtime_windows_diagnostics import redact_diagnostic_text

RUNTIME_FRESHNESS = timedelta(seconds=90)
RUNTIME_FUTURE_TOLERANCE = timedelta(minutes=5)


@dataclass(frozen=True, slots=True)
class RuntimeStatusProjection:
    state: str
    updated_at: datetime | None
    healthy: bool
    read_state: RuntimeStatusReadState
    lines: tuple[str, ...]


def project_runtime_status(
    read: RuntimeStatusRead,
    *,
    now: datetime,
) -> RuntimeStatusProjection:
    if read.status is None:
        return _unavailable_projection(read)
    status = read.status
    updated_at = _aware_instant(status.updated_at)
    current_time = _aware_instant(now)
    if updated_at is None or current_time is None:
        return _invalid_timestamp_projection(read)
    updated_at = updated_at.astimezone(UTC)
    current_time = current_time.astimezone(UTC)
    if updated_at > current_time + RUNTIME_FUTURE_TOLERANCE:
        return _invalid_timestamp_projection(read)
    age = max(0, int((current_time - updated_at).total_seconds()))
    process_alive = Path(f"/proc/{status.pid}").is_dir()
    runtime_state = _runtime_state(status, age=age, process_alive=process_alive)
    failures = _health_failures(
        status,
        now=current_time,
        updated_at=updated_at,
        age=age,
        process_alive=process_alive,
    )
    lines = [
        "runtime_status_read_state=available",
        f"wsl_process_state={runtime_state}",
        f"feed_session_state={status.feed_state}",
        f"projection_state={status.projection_state}",
        f"completed_day_state={status.completed_day_state}",
        f"runtime_pid={status.pid}",
        f"runtime_heartbeat_age_seconds={age}",
        f"runtime_health_state={'healthy' if not failures else 'insufficient'}",
    ]
    lines.extend(f"runtime_health_failure={failure}" for failure in failures)
    _append_runtime_evidence(lines, status)
    return RuntimeStatusProjection(
        state=runtime_state,
        updated_at=updated_at,
        healthy=not failures,
        read_state=read.state,
        lines=tuple(lines),
    )


def _runtime_state(
    status: RealtimeRuntimeStatus,
    *,
    age: int,
    process_alive: bool,
) -> str:
    if status.process_state != "running":
        return status.process_state
    if status.state in {"stopped", "error", "blocked", "reconciled"}:
        return status.state
    if process_alive and age <= RUNTIME_FRESHNESS.total_seconds():
        return status.state
    return "stale_process"


def _health_failures(
    status: RealtimeRuntimeStatus,
    *,
    now: datetime,
    updated_at: datetime,
    age: int,
    process_alive: bool,
) -> tuple[str, ...]:
    failures: list[str] = []
    if age > RUNTIME_FRESHNESS.total_seconds():
        failures.append("runtime_stale")
    if status.process_state != "running" or not process_alive:
        failures.append("process_not_running")
    if status.state in {"blocked", "connecting", "error", "recovering", "stopped"}:
        failures.append("runtime_state_not_healthy")
    if status.feed_state not in {"connected", "reconciled"}:
        failures.append("feed_not_healthy")
    if not status.session_id:
        failures.append("session_missing")
    if status.last_error is not None:
        failures.append("runtime_error_present")
    if not _fresh_evidence(
        status.last_successful_heartbeat_at,
        now=now,
        updated_at=updated_at,
    ):
        failures.append("successful_heartbeat_missing_or_stale")
    if status.messages <= 0 or not _valid_activity_evidence(
        status.last_message_at,
        now=now,
        updated_at=updated_at,
    ):
        failures.append("message_evidence_missing")
    if status.microbatches <= 0 or not _valid_activity_evidence(
        status.last_microbatch_at,
        now=now,
        updated_at=updated_at,
    ):
        failures.append("microbatch_evidence_missing")
    return tuple(failures)


def _fresh_evidence(
    value: str | None,
    *,
    now: datetime,
    updated_at: datetime,
) -> bool:
    instant = _aware_instant(value)
    if instant is None:
        return False
    age = now.astimezone(UTC) - instant.astimezone(UTC)
    return timedelta(0) <= age <= RUNTIME_FRESHNESS and instant.astimezone(
        UTC
    ) <= updated_at.astimezone(UTC)


def _valid_activity_evidence(
    value: str | None,
    *,
    now: datetime,
    updated_at: datetime,
) -> bool:
    instant = _aware_instant(value)
    if instant is None:
        return False
    normalized = instant.astimezone(UTC)
    return normalized <= now.astimezone(UTC) and normalized <= updated_at.astimezone(UTC)


def _aware_instant(value: str | datetime | None) -> datetime | None:
    if isinstance(value, datetime):
        instant = value
    elif isinstance(value, str):
        try:
            instant = datetime.fromisoformat(value)
        except ValueError:
            return None
    else:
        return None
    return instant if instant.tzinfo is not None and instant.utcoffset() is not None else None


def _unavailable_projection(read: RuntimeStatusRead) -> RuntimeStatusProjection:
    process_state = "not_running" if read.state == "missing" else "invalid_runtime_status"
    lines = [
        f"runtime_status_read_state={read.state}",
        f"wsl_process_state={process_state}",
        "feed_session_state=not_started",
        "projection_state=not_available",
        "completed_day_state=unknown",
        "runtime_health_state=insufficient",
    ]
    if read.error_code is not None:
        lines.append(f"runtime_status_read_error={read.error_code}")
    return RuntimeStatusProjection(
        state=process_state,
        updated_at=None,
        healthy=False,
        read_state=read.state,
        lines=tuple(lines),
    )


def _invalid_timestamp_projection(read: RuntimeStatusRead) -> RuntimeStatusProjection:
    return RuntimeStatusProjection(
        state="invalid_runtime_status",
        updated_at=None,
        healthy=False,
        read_state=read.state,
        lines=(
            "runtime_status_read_state=available",
            "wsl_process_state=invalid_runtime_status",
            "runtime_timestamp_state=invalid",
            "feed_session_state=not_started",
            "projection_state=not_available",
            "completed_day_state=unknown",
            "runtime_health_state=insufficient",
        ),
    )


def _append_runtime_evidence(
    lines: list[str],
    status: RealtimeRuntimeStatus,
) -> None:
    for name, output_name in (
        ("market_date", "market_date"),
        ("session_id", "session_id"),
        ("last_successful_heartbeat_at", "last_successful_heartbeat"),
        ("last_message_at", "last_message_at"),
        ("last_microbatch_at", "last_microbatch_at"),
    ):
        value = getattr(status, name)
        if value:
            lines.append(f"runtime_{output_name}={value}")
    lines.extend(
        (
            f"runtime_messages={status.messages}",
            f"runtime_microbatches={status.microbatches}",
        )
    )
    if status.exit_code is not None:
        lines.append(f"runtime_exit_code={status.exit_code}")
    if status.last_error:
        lines.extend(
            (
                "runtime_failure_origin=python_feed_error",
                f"runtime_last_error={redact_diagnostic_text(status.last_error)}",
            )
        )
    for index, failure in enumerate(status.retry_failures, start=1):
        safe_failure = redact_diagnostic_text(json.dumps(failure, ensure_ascii=False))
        lines.append(f"retry_failure_{index}={safe_failure}")
    if status.log_path:
        lines.append(f"runtime_log_path={status.log_path}")
    if status.recovery_action:
        lines.append("runtime_recovery_action=" + redact_diagnostic_text(status.recovery_action))
    elif status.last_error:
        lines.append("runtime_recovery_action=读取 service.log 与具体 Python feed 根因后恢复")


__all__ = [
    "RuntimeStatusProjection",
    "project_runtime_status",
]
