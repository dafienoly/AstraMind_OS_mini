from __future__ import annotations

import json
import os
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import pytest

from astramind_mini.local_ops.realtime_service_deployment import TASK_NAME
from astramind_mini.local_ops.realtime_service_diagnostics import realtime_status_lines
from astramind_mini.local_ops.realtime_windows_diagnostics import (
    parse_windows_wrapper_diagnostic,
)

NOW = datetime(2026, 7, 31, 3, 0, tzinfo=UTC)
ATTEMPT_ID = "79c25630-2900-45e9-91c4-c43ea0b00090"


def test_older_wrapper_failure_is_historical_after_healthy_runtime(tmp_path: Path) -> None:
    local_app_data = _write_wrapper(
        tmp_path,
        state="wsl_native_exit",
        updated_at=NOW - timedelta(seconds=30),
    )
    _write_runtime(tmp_path, state="running", updated_at=NOW - timedelta(seconds=10))

    rendered = _status(tmp_path, local_app_data, last_result="0")

    assert "wrapper_historical_failure=true" in rendered
    assert "wrapper_historical_failure_origin=wsl_native_exit" in rendered
    assert "\nwrapper_failure_origin=" not in rendered
    assert "\nwrapper_recovery_action=" not in rendered
    assert "wrapper_timestamp_state=superseded" in rendered
    assert "service_operational_state=running" in rendered


def test_newer_wrapper_failure_blocks_older_healthy_runtime(tmp_path: Path) -> None:
    local_app_data = _write_wrapper(
        tmp_path,
        state="wrapper_launch_exception",
        updated_at=NOW - timedelta(seconds=10),
    )
    _write_runtime(tmp_path, state="running", updated_at=NOW - timedelta(seconds=30))

    rendered = _status(tmp_path, local_app_data, last_result="0")

    assert "wrapper_historical_failure=false" in rendered
    assert "service_operational_state=blocked" in rendered


def test_stale_runtime_cannot_supersede_older_wrapper_failure(tmp_path: Path) -> None:
    local_app_data = _write_wrapper(
        tmp_path,
        state="wsl_native_exit",
        updated_at=NOW - timedelta(minutes=10),
    )
    _write_runtime(tmp_path, state="running", updated_at=NOW - timedelta(minutes=9))

    rendered = _status(tmp_path, local_app_data, last_result="0")

    assert "wrapper_historical_failure=false" in rendered
    assert "wsl_process_state=stale_process" in rendered
    assert "service_operational_state=blocked" in rendered


def test_equal_wrapper_and_runtime_timestamps_fail_closed(tmp_path: Path) -> None:
    local_app_data = _write_wrapper(
        tmp_path,
        state="wsl_native_exit",
        updated_at=NOW - timedelta(seconds=10),
    )
    _write_runtime(tmp_path, state="running", updated_at=NOW - timedelta(seconds=10))

    rendered = _status(tmp_path, local_app_data, last_result="0")

    assert "wrapper_historical_failure=false" in rendered
    assert "service_operational_state=blocked" in rendered


@pytest.mark.parametrize(
    "updated_at",
    [
        "not-a-timestamp",
        "2026-07-31T03:00:00",
        (NOW + timedelta(minutes=6)).isoformat(),
    ],
)
def test_invalid_wrapper_timestamp_is_unknown_not_current_failure(
    tmp_path: Path,
    updated_at: str,
) -> None:
    local_app_data = _write_wrapper(
        tmp_path,
        state="wsl_native_exit",
        updated_at=updated_at,
    )
    _write_runtime(tmp_path, state="running", updated_at=NOW - timedelta(seconds=5))

    rendered = _status(tmp_path, local_app_data, last_result="0")

    assert "wrapper_status_read_state=invalid" in rendered
    assert "wrapper_state=invalid_diagnostic" in rendered
    assert "wrapper_failure_origin=" not in rendered
    assert "service_operational_state=unknown" in rendered


@pytest.mark.parametrize("state", ["running", "completed"])
def test_stale_nonfailure_wrapper_does_not_prove_health(
    tmp_path: Path,
    state: str,
) -> None:
    local_app_data = _write_wrapper(
        tmp_path,
        state=state,
        updated_at=NOW - timedelta(minutes=10),
    )

    rendered = _status(tmp_path, local_app_data, last_result="0")

    assert "wrapper_timestamp_state=stale" in rendered
    assert "runtime_status_read_state=missing" in rendered
    assert "service_operational_state=blocked" in rendered


def test_scheduler_nonzero_result_still_blocks_historical_wrapper_failure(
    tmp_path: Path,
) -> None:
    local_app_data = _write_wrapper(
        tmp_path,
        state="wsl_native_exit",
        updated_at=NOW - timedelta(seconds=30),
    )
    _write_runtime(tmp_path, state="running", updated_at=NOW - timedelta(seconds=10))

    rendered = _status(tmp_path, local_app_data, last_result="-196608")

    assert "wrapper_historical_failure=true" in rendered
    assert "scheduler_execution_state=failed" in rendered
    assert "service_operational_state=blocked" in rendered


def test_wrapper_read_distinguishes_missing_and_unreadable(tmp_path: Path) -> None:
    missing = _status(tmp_path, tmp_path / "missing", last_result="0")
    unreadable_local = tmp_path / "unreadable"
    unreadable_status = unreadable_local / "AstraMindOSMini/realtime-task-status.json"
    unreadable_status.mkdir(parents=True)
    unreadable = _status(tmp_path, unreadable_local, last_result="0")

    assert "wrapper_status_read_state=missing" in missing
    assert "wrapper_status_read_error=status_file_missing" in missing
    assert "wrapper_status_read_state=unreadable" in unreadable
    assert "wrapper_status_read_error=IsADirectoryError" in unreadable


def test_parser_canonicalizes_aware_timestamp_and_attempt_id() -> None:
    diagnostic = parse_windows_wrapper_diagnostic(
        json.dumps(
            {
                "schema_version": 2,
                "state": "running",
                "updated_at": "2026-07-31T11:00:00+08:00",
                "attempt_id": ATTEMPT_ID.upper(),
            }
        ),
        now=NOW,
    )

    assert diagnostic.updated_at == "2026-07-31T03:00:00+00:00"
    assert diagnostic.updated_at_instant == NOW
    assert diagnostic.attempt_id == str(UUID(ATTEMPT_ID))


def _write_wrapper(
    root: Path,
    *,
    state: str,
    updated_at: datetime | str,
) -> Path:
    local_app_data = root / "windows-local"
    status_root = local_app_data / "AstraMindOSMini"
    status_root.mkdir(parents=True, exist_ok=True)
    timestamp = updated_at.isoformat() if isinstance(updated_at, datetime) else updated_at
    (status_root / "realtime-task-status.json").write_text(
        json.dumps(
            {
                "schema_version": 2,
                "state": state,
                "updated_at": timestamp,
                "attempt_id": ATTEMPT_ID,
                "native_exit_code": 17 if "exception" in state or "exit" in state else 0,
                "exception_type": "System.Runtime.InteropServices.COMException"
                if state == "wrapper_launch_exception"
                else None,
                "exception_message": "launch failed"
                if state == "wrapper_launch_exception"
                else None,
            }
        ),
        encoding="utf-8",
    )
    return local_app_data


def _write_runtime(
    root: Path,
    *,
    state: str,
    updated_at: datetime,
    overrides: dict[str, object] | None = None,
) -> None:
    control_root = root / "control"
    control_root.mkdir(parents=True, exist_ok=True)
    payload: dict[str, object] = {
        "state": state,
        "updated_at": updated_at.isoformat(),
        "pid": os.getpid(),
        "process_state": "running",
        "feed_state": "connected",
        "projection_state": "active",
        "completed_day_state": "unknown",
        "session_id": "sha256:" + "1" * 64,
        "messages": 1,
        "microbatches": 1,
        "last_successful_heartbeat_at": updated_at.isoformat(),
        "last_message_at": updated_at.isoformat(),
        "last_microbatch_at": updated_at.isoformat(),
        "last_error": None,
    }
    payload.update(overrides or {})
    (control_root / "status.json").write_text(
        json.dumps(payload),
        encoding="utf-8",
    )


def _status(root: Path, local_app_data: Path, *, last_result: str) -> str:
    completed = subprocess.CompletedProcess(
        [],
        0,
        f"任务名: \\{TASK_NAME}\n上次结果: {last_result}\n",
        "",
    )
    return "\n".join(
        realtime_status_lines(
            completed,
            control_root=root / "control",
            environ={"LOCALAPPDATA": str(local_app_data)},
            now=NOW,
        )
    )
