"""Independent scheduler, Windows-wrapper, and Python-feed diagnostics."""

from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path

from astramind_mini.local_ops.realtime_runtime_diagnostics import (
    project_runtime_status,
)
from astramind_mini.local_ops.realtime_runtime_status import (
    read_runtime_status,
)
from astramind_mini.local_ops.realtime_service_deployment import (
    TASK_NAME,
    scheduler_query_state,
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
    runtime = project_runtime_status(
        read_runtime_status(control_root / "status.json"),
        now=current_time,
    )
    wrapper_timing = correlate_wrapper_timing(
        wrapper_read.diagnostic,
        runtime_updated_at=runtime.updated_at,
        runtime_healthy=runtime.healthy,
        now=current_time,
    )
    lines.extend(wrapper_status_lines(wrapper_read, wrapper_timing))
    lines.extend(runtime.lines)
    lines.append(
        "service_operational_state="
        + resolve_operational_state(
            scheduler_state,
            last_result,
            wrapper_read,
            runtime.state,
            runtime.read_state,
            wrapper_timing,
        )
    )
    lines.append("broker_actions_allowed=false")
    return tuple(lines)


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
