"""Independent scheduler, Windows-wrapper, and Python-feed diagnostics."""

from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path

from astramind_mini.local_ops.realtime_service_deployment import (
    TASK_NAME,
    scheduler_query_state,
)
from astramind_mini.local_ops.realtime_service_runtime import (
    RealtimeRuntimeStatus,
    RealtimeStatusStore,
)
from astramind_mini.local_ops.realtime_windows_diagnostics import (
    read_windows_wrapper_diagnostic_result,
    redact_diagnostic_text,
)
from astramind_mini.local_ops.realtime_wrapper_status import (
    correlate_wrapper_timing,
    resolve_operational_state,
    wrapper_status_lines,
)


def realtime_status_lines(
    completed: subprocess.CompletedProcess[str],
    *,
    control_root: Path = Path("var/control/realtime-market-service"),
    environ: Mapping[str, str] | None = None,
    now: datetime | None = None,
) -> tuple[str, ...]:
    scheduler_state = scheduler_query_state(
        completed.returncode,
        completed.stdout,
        completed.stderr,
    )
    fact_path = control_root / "scheduler-fact.json"
    previous = _read_scheduler_fact(fact_path)
    if scheduler_state != "query_failed":
        _write_scheduler_fact(fact_path, scheduler_state)
    lines = [f"state={scheduler_state}", f"scheduler_state={scheduler_state}"]
    lines.append(f"task_name={TASK_NAME}")
    if scheduler_state == "query_failed" and previous is not None:
        lines.extend(
            (
                f"last_known_task_state={previous['state']}",
                f"last_known_installed={str(previous['state'] == 'installed').lower()}",
                f"last_known_task_checked_at={previous['checked_at']}",
            )
        )
    message = redact_diagnostic_text(completed.stderr or completed.stdout)
    if message and scheduler_state in {"installed", "query_failed"}:
        lines.append("scheduler_message=" + " ".join(message.splitlines()))
    lines.append(f"scheduler_exit_code={completed.returncode}")
    last_result = _scheduler_field(completed.stdout, "上次结果", "Last Result")
    lines.extend(_scheduler_result_lines(last_result))
    current_time = datetime.now(UTC) if now is None else now.astimezone(UTC)
    wrapper_read = read_windows_wrapper_diagnostic_result(
        environ=environ,
        now=current_time,
    )
    runtime = RealtimeStatusStore(control_root).read()
    runtime_state, runtime_updated_at, runtime_healthy, runtime_lines = _runtime_lines(
        runtime,
        now=current_time,
    )
    wrapper_timing = correlate_wrapper_timing(
        wrapper_read.diagnostic,
        runtime_updated_at=runtime_updated_at,
        runtime_healthy=runtime_healthy,
        now=current_time,
    )
    lines.extend(wrapper_status_lines(wrapper_read, wrapper_timing))
    lines.extend(runtime_lines)
    lines.append(
        "service_operational_state="
        + resolve_operational_state(
            scheduler_state,
            last_result,
            wrapper_read,
            runtime_state,
            wrapper_timing,
        )
    )
    lines.append("broker_actions_allowed=false")
    return tuple(lines)


def _runtime_lines(
    runtime: RealtimeRuntimeStatus | None,
    *,
    now: datetime,
) -> tuple[str, datetime | None, bool, tuple[str, ...]]:
    if runtime is None:
        return (
            "not_running",
            None,
            False,
            (
                "wsl_process_state=not_running",
                "feed_session_state=not_started",
                "projection_state=not_available",
                "completed_day_state=unknown",
            ),
        )
    try:
        updated_at = datetime.fromisoformat(runtime.updated_at)
    except (TypeError, ValueError):
        return _invalid_runtime_timestamp()
    if updated_at.tzinfo is None or updated_at.utcoffset() is None:
        return _invalid_runtime_timestamp()
    updated_at = updated_at.astimezone(UTC)
    current_time = now.astimezone(UTC)
    if updated_at > current_time + timedelta(minutes=5):
        return _invalid_runtime_timestamp()
    age = max(
        0,
        int((current_time - updated_at).total_seconds()),
    )
    process_alive = Path(f"/proc/{runtime.pid}").is_dir()
    terminal = runtime.process_state == "exited" or runtime.state in {
        "stopped",
        "error",
        "blocked",
        "reconciled",
    }
    runtime_state = runtime.state if terminal or (process_alive and age <= 90) else "stale_process"
    lines = [
        f"wsl_process_state={runtime_state}",
        f"feed_session_state={runtime.feed_state}",
        f"projection_state={runtime.projection_state}",
        f"completed_day_state={runtime.completed_day_state}",
        f"runtime_pid={runtime.pid}",
        f"runtime_heartbeat_age_seconds={age}",
    ]
    _append_runtime_evidence(lines, runtime)
    healthy = (
        age <= 90
        and runtime_state
        not in {
            "blocked",
            "connecting",
            "error",
            "not_running",
            "recovering",
            "stale_process",
            "stopped",
        }
        and runtime.last_error is None
    )
    return runtime_state, updated_at, healthy, tuple(lines)


def _invalid_runtime_timestamp() -> tuple[str, None, bool, tuple[str, ...]]:
    return (
        "invalid_runtime_status",
        None,
        False,
        (
            "wsl_process_state=invalid_runtime_status",
            "runtime_timestamp_state=invalid",
            "feed_session_state=unknown",
            "projection_state=not_available",
            "completed_day_state=unknown",
        ),
    )


def _append_runtime_evidence(lines: list[str], runtime: RealtimeRuntimeStatus) -> None:
    for name, output_name in (
        ("market_date", "market_date"),
        ("session_id", "session_id"),
        ("last_successful_heartbeat_at", "last_successful_heartbeat"),
        ("last_message_at", "last_message_at"),
        ("last_microbatch_at", "last_microbatch_at"),
    ):
        value = getattr(runtime, name)
        if value:
            lines.append(f"runtime_{output_name}={value}")
    lines.extend(
        (
            f"runtime_messages={runtime.messages}",
            f"runtime_microbatches={runtime.microbatches}",
        )
    )
    if runtime.exit_code is not None:
        lines.append(f"runtime_exit_code={runtime.exit_code}")
    if runtime.last_error:
        lines.extend(
            (
                "runtime_failure_origin=python_feed_error",
                f"runtime_last_error={redact_diagnostic_text(runtime.last_error)}",
            )
        )
    for index, failure in enumerate(runtime.retry_failures, start=1):
        safe_failure = redact_diagnostic_text(json.dumps(failure, ensure_ascii=False))
        lines.append(f"retry_failure_{index}={safe_failure}")
    if runtime.log_path:
        lines.append(f"runtime_log_path={runtime.log_path}")
    if runtime.recovery_action:
        lines.append(f"runtime_recovery_action={redact_diagnostic_text(runtime.recovery_action)}")
    elif runtime.last_error:
        lines.append("runtime_recovery_action=读取 service.log 与具体 Python feed 根因后恢复")


def _scheduler_result_lines(last_result: str | None) -> tuple[str, ...]:
    if last_result is None:
        return ()
    lines = [f"scheduler_last_result={last_result}"]
    if last_result in {"267009", "0x41301"}:
        lines.append("scheduler_execution_state=running")
    elif last_result in {"0", "0x0"}:
        lines.append("scheduler_execution_state=completed")
    else:
        lines.extend(
            (
                "scheduler_execution_state=failed",
                "scheduler_recovery_action=检查包装器诊断、原生 WSL 退出码与 Python feed 状态",
            )
        )
    return tuple(lines)


def _scheduler_field(payload: str, *labels: str) -> str | None:
    folded_labels = {label.casefold() for label in labels}
    for line in payload.splitlines():
        name, separator, value = line.partition(":")
        if separator and name.strip().casefold() in folded_labels:
            return value.strip()
    return None


def _read_scheduler_fact(path: Path) -> dict[str, str] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None
    if value.get("state") not in {"installed", "not_installed"}:
        return None
    return {"state": str(value["state"]), "checked_at": str(value["checked_at"])}


def _write_scheduler_fact(path: Path, state: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(
            {"state": state, "checked_at": datetime.now(UTC).isoformat()},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    os.replace(temporary, path)


__all__ = [
    "realtime_status_lines",
]
