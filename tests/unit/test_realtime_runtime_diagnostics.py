from __future__ import annotations

import json
import os
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from astramind_mini.local_ops.realtime_service_deployment import TASK_NAME
from astramind_mini.local_ops.realtime_service_diagnostics import realtime_status_lines

NOW = datetime(2026, 7, 31, 3, 0, tzinfo=UTC)
ATTEMPT_ID = "79c25630-2900-45e9-91c4-c43ea0b00090"


@pytest.mark.parametrize(
    ("runtime_overrides", "expected_failure"),
    [
        ({"process_state": "exited"}, "process_not_running"),
        ({"feed_state": "not_started"}, "feed_not_healthy"),
        ({"session_id": None}, "session_missing"),
        ({"last_successful_heartbeat_at": None}, "successful_heartbeat_missing_or_stale"),
        (
            {"last_successful_heartbeat_at": (NOW + timedelta(seconds=1)).isoformat()},
            "successful_heartbeat_missing_or_stale",
        ),
        ({"messages": 0}, "message_evidence_missing"),
        ({"last_message_at": (NOW + timedelta(seconds=1)).isoformat()}, "message_evidence_missing"),
        ({"microbatches": 0}, "microbatch_evidence_missing"),
    ],
)
def test_superficially_new_runtime_cannot_hide_older_wrapper_failure(
    tmp_path: Path,
    runtime_overrides: dict[str, object],
    expected_failure: str,
) -> None:
    local_app_data = _write_wrapper(tmp_path, NOW - timedelta(seconds=30))
    _write_runtime(
        tmp_path,
        updated_at=NOW - timedelta(seconds=10),
        overrides=runtime_overrides,
    )

    rendered = _status(tmp_path, local_app_data)

    assert "wrapper_historical_failure=false" in rendered
    assert f"runtime_health_failure={expected_failure}" in rendered
    assert "service_operational_state=blocked" in rendered


def test_stale_successful_heartbeat_cannot_hide_older_wrapper_failure(
    tmp_path: Path,
) -> None:
    local_app_data = _write_wrapper(tmp_path, NOW - timedelta(minutes=3))
    _write_runtime(
        tmp_path,
        updated_at=NOW - timedelta(seconds=10),
        overrides={
            "last_successful_heartbeat_at": (NOW - timedelta(minutes=2)).isoformat(),
        },
    )

    rendered = _status(tmp_path, local_app_data)

    assert "runtime_health_failure=successful_heartbeat_missing_or_stale" in rendered
    assert "wrapper_historical_failure=false" in rendered
    assert "service_operational_state=blocked" in rendered


@pytest.mark.parametrize(
    ("setup", "expected_state", "expected_error"),
    [
        ("missing", "missing", "status_file_missing"),
        ("corrupt", "invalid", "JSONDecodeError"),
        ("schema", "invalid", "ValueError"),
        ("directory", "unreadable", "IsADirectoryError"),
    ],
)
def test_runtime_status_read_failures_are_blocked_and_layered(
    tmp_path: Path,
    setup: str,
    expected_state: str,
    expected_error: str,
) -> None:
    control_root = tmp_path / "control"
    control_root.mkdir()
    status_path = control_root / "status.json"
    if setup == "corrupt":
        status_path.write_text("{broken", encoding="utf-8")
    elif setup == "schema":
        status_path.write_text('{"state":"running"}', encoding="utf-8")
    elif setup == "directory":
        status_path.mkdir()

    rendered = _status(tmp_path, tmp_path / "missing")

    assert f"runtime_status_read_state={expected_state}" in rendered
    assert f"runtime_status_read_error={expected_error}" in rendered
    assert "feed_session_state=not_started" in rendered
    assert "service_operational_state=blocked" in rendered
    assert "broker_actions_allowed=false" in rendered


def test_runtime_permission_error_is_stably_reported(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    control_root = tmp_path / "control"
    control_root.mkdir()
    status_path = control_root / "status.json"
    status_path.write_text("{}", encoding="utf-8")
    original_read_text = Path.read_text

    def denied(
        path: Path,
        encoding: str | None = None,
        errors: str | None = None,
    ) -> str:
        if path == status_path:
            raise PermissionError("private path")
        return original_read_text(path, encoding=encoding, errors=errors)

    monkeypatch.setattr(Path, "read_text", denied)

    rendered = _status(tmp_path, tmp_path / "missing")

    assert "runtime_status_read_state=unreadable" in rendered
    assert "runtime_status_read_error=PermissionError" in rendered
    assert "private path" not in rendered
    assert "service_operational_state=blocked" in rendered


def _write_wrapper(root: Path, updated_at: datetime) -> Path:
    local_app_data = root / "windows-local"
    status_root = local_app_data / "AstraMindOSMini"
    status_root.mkdir(parents=True)
    (status_root / "realtime-task-status.json").write_text(
        json.dumps(
            {
                "schema_version": 2,
                "state": "wsl_native_exit",
                "updated_at": updated_at.isoformat(),
                "attempt_id": ATTEMPT_ID,
                "native_exit_code": 17,
            }
        ),
        encoding="utf-8",
    )
    return local_app_data


def _write_runtime(
    root: Path,
    *,
    updated_at: datetime,
    overrides: dict[str, object],
) -> None:
    control_root = root / "control"
    control_root.mkdir(parents=True, exist_ok=True)
    payload: dict[str, object] = {
        "state": "running",
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
    payload.update(overrides)
    (control_root / "status.json").write_text(json.dumps(payload), encoding="utf-8")


def _status(root: Path, local_app_data: Path) -> str:
    completed = subprocess.CompletedProcess(
        [],
        0,
        f"任务名: \\{TASK_NAME}\n上次结果: 0\n",
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
