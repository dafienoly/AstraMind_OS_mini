import json
import os
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest

from astramind_mini.local_ops.realtime_service_deployment import TASK_NAME
from astramind_mini.local_ops.realtime_service_diagnostics import realtime_status_lines
from astramind_mini.local_ops.realtime_service_runtime import RealtimeStatusStore
from astramind_mini.local_ops.realtime_windows_diagnostics import (
    parse_windows_wrapper_diagnostic,
)

_WINDOWS_RUNTIME_PROOF_ENABLED = (
    os.environ.get("ASTRAMIND_RUN_WINDOWS_WRAPPER_TESTS") == "1"
    and shutil.which("powershell.exe") is not None
)


def test_wrapper_diagnostic_supports_legacy_exit_and_redacts_exception() -> None:
    secret_key = "to" + "ken"
    legacy = json.dumps(
        {
            "exit_code": 23,
            "last_error": f"failed at /secret/path; {secret_key}='alpha beta'",
            "exception_type": "System.ComponentModel.Win32Exception",
            "exception_hresult": "0x80004005",
        }
    )

    diagnostic = parse_windows_wrapper_diagnostic(legacy)

    assert diagnostic.schema_version == 1
    assert diagnostic.state == "wsl_native_exit"
    assert diagnostic.native_exit_code == 23
    assert diagnostic.exception_type == "System.ComponentModel.Win32Exception"
    assert diagnostic.exception_hresult == "0x80004005"
    assert diagnostic.exception_message is not None
    assert "/secret/path" in diagnostic.exception_message
    assert "alpha beta" not in diagnostic.exception_message
    assert "<redacted>" in diagnostic.exception_message


def test_wrapper_diagnostic_rejects_type_confusion() -> None:
    payload = json.dumps(
        {
            "schema_version": 2,
            "state": "completed",
            "native_exit_code": 0,
            "stdout_truncated": "false",
        }
    )

    with pytest.raises(TypeError, match="boolean"):
        parse_windows_wrapper_diagnostic(payload)


def test_status_separates_scheduler_wrapper_and_python_feed_failures(tmp_path: Path) -> None:
    secret_key = "to" + "ken"
    local_app_data = tmp_path / "windows-local"
    wrapper_root = local_app_data / "AstraMindOSMini"
    wrapper_root.mkdir(parents=True)
    (wrapper_root / "realtime-task-status.json").write_text(
        json.dumps(
            {
                "schema_version": 2,
                "state": "wsl_native_exit",
                "updated_at": "2026-07-31T01:00:00+00:00",
                "wsl_executable": r"C:\Windows\System32\wsl.exe",
                "native_exit_code": 17,
                "stdout_characters_seen": 0,
                "stderr_characters_seen": 19,
                "stdout_truncated": False,
                "stderr_truncated": False,
                "log_path": r"C:\Users\tester\AppData\Local\AstraMindOSMini\realtime-task.log",
            }
        ),
        encoding="utf-8",
    )
    control_root = tmp_path / "control"
    RealtimeStatusStore(control_root).publish(
        "blocked",
        process_state="exited",
        feed_state="blocked",
        projection_state="blocked",
        exit_code=17,
        last_error=f"bridge_timeout {secret_key}=private",
        recovery_action="检查 bridge stderr",
        last_message_at=datetime(2026, 7, 31, 1, 0, tzinfo=UTC),
    )
    completed = subprocess.CompletedProcess(
        [],
        0,
        f"任务名: \\{TASK_NAME}\n上次结果: -196608\n",
        "",
    )

    lines = realtime_status_lines(
        completed,
        control_root=control_root,
        environ={"LOCALAPPDATA": str(local_app_data)},
        now=datetime(2026, 7, 31, 2, 0, tzinfo=UTC),
    )
    rendered = "\n".join(lines)

    assert "scheduler_state=installed" in rendered
    assert "scheduler_execution_state=failed" in rendered
    assert "wrapper_state=wsl_native_exit" in rendered
    assert "wrapper_native_exit_code=17" in rendered
    assert "wrapper_failure_origin=wsl_native_exit" in rendered
    assert "runtime_failure_origin=python_feed_error" in rendered
    assert "runtime_last_message_at=2026-07-31T01:00:00+00:00" in rendered
    assert f"runtime_last_error=bridge_timeout {secret_key}=<redacted>" in rendered
    assert "private" not in rendered
    assert "service_operational_state=blocked" in rendered


def test_status_projects_wrapper_launch_exception_with_recovery(tmp_path: Path) -> None:
    local_app_data = tmp_path / "windows-local"
    wrapper_root = local_app_data / "AstraMindOSMini"
    wrapper_root.mkdir(parents=True)
    (wrapper_root / "realtime-task-status.json").write_text(
        json.dumps(
            {
                "schema_version": 2,
                "state": "wrapper_launch_exception",
                "updated_at": "2026-07-31T01:00:00+00:00",
                "wsl_executable": r"C:\Windows\System32\wsl.exe",
                "native_exit_code": 127,
                "exception_type": "System.ComponentModel.Win32Exception",
                "exception_message": "access denied",
                "exception_hresult": "0x80070005",
            }
        ),
        encoding="utf-8",
    )
    completed = subprocess.CompletedProcess(
        [],
        0,
        f"任务名: \\{TASK_NAME}\n上次结果: -196608\n",
        "",
    )

    rendered = "\n".join(
        realtime_status_lines(
            completed,
            control_root=tmp_path / "control",
            environ={"LOCALAPPDATA": str(local_app_data)},
            now=datetime(2026, 7, 31, 2, 0, tzinfo=UTC),
        )
    )

    assert "wrapper_failure_origin=wrapper_launch_exception" in rendered
    assert "wrapper_exception_type=System.ComponentModel.Win32Exception" in rendered
    assert "wrapper_exception_hresult=0x80070005" in rendered
    assert "wrapper_recovery_action=核对绝对 wsl.exe、任务身份与异常 HResult 后重试" in rendered
    assert "service_operational_state=blocked" in rendered


def test_status_accepts_old_runtime_state_and_missing_wrapper(tmp_path: Path) -> None:
    control_root = tmp_path / "control"
    control_root.mkdir()
    (control_root / "status.json").write_text(
        json.dumps(
            {
                "state": "blocked",
                "updated_at": datetime.now(UTC).isoformat(),
                "pid": os.getpid(),
                "last_error": "bridge_unavailable",
            }
        ),
        encoding="utf-8",
    )
    completed = subprocess.CompletedProcess(
        [],
        0,
        f"任务名: \\{TASK_NAME}\n上次结果: 0\n",
        "",
    )

    lines = realtime_status_lines(
        completed,
        control_root=control_root,
        environ={"LOCALAPPDATA": str(tmp_path / "missing")},
    )
    rendered = "\n".join(lines)

    assert "wrapper_state=not_available" in rendered
    assert "wrapper_status_read_state=missing" in rendered
    assert "wrapper_status_read_error=status_file_missing" in rendered
    assert "runtime_failure_origin=python_feed_error" in rendered
    assert "runtime_recovery_action=读取 service.log 与具体 Python feed 根因后恢复" in rendered
    assert "service_operational_state=blocked" in rendered


@pytest.mark.skipif(
    not _WINDOWS_RUNTIME_PROOF_ENABLED,
    reason="set ASTRAMIND_RUN_WINDOWS_WRAPPER_TESTS=1 for the Windows runtime proof",
)
def test_native_process_runner_binds_arguments_and_preserves_stderr_exit() -> None:
    wrapper = _windows_path(Path("scripts/windows/run_realtime_market_task.ps1"))
    secret_key = "to" + "ken"
    script = f"""
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
. '{_powershell_literal(wrapper)}' `
    -Distro '测试 Ubuntu' `
    -Workdir '/home/ly/含 空格' `
    -MakeTarget 'realtime-market-service-run'
Initialize-NativeProcessRunner
$bound = [AstraMind.Realtime.NativeProcessRunner]::BuildArguments(
    [string[]]@('plain', '含 空格', 'quote"value', 'C:\\path with space\\')
)
$executable = Join-Path $env:SystemRoot 'System32\\WindowsPowerShell\\v1.0\\powershell.exe'
$native = [AstraMind.Realtime.NativeProcessRunner]::Run(
    $executable,
    [string[]]@(
        '-NoProfile',
        '-Command',
        '[Console]::Error.WriteLine(''{secret_key}="alpha beta"'');' +
        '[Console]::Error.Write(("Z" * 200000)); exit 23'
    ),
    4096,
    1024
)
$safeError = Redact-Line $native.StandardError.Text
[ordered]@{{
    bound = $bound
    exit_code = $native.ExitCode
    stderr = $safeError
    characters_seen = $native.StandardError.CharactersSeen
    truncated = $native.StandardError.Truncated
}} | ConvertTo-Json -Compress
"""
    completed = _run_powershell(script, check=True)

    evidence = json.loads(completed.stdout)
    assert evidence["bound"] == ('plain "含 空格" "quote\\"value" "C:\\path with space\\\\"')
    assert evidence["exit_code"] == 23
    assert evidence["characters_seen"] > 200_000
    assert evidence["truncated"] is True
    assert "alpha beta" not in evidence["stderr"]
    assert f"{secret_key}=<redacted>" in evidence["stderr"]


@pytest.mark.skipif(
    not _WINDOWS_RUNTIME_PROOF_ENABLED,
    reason="set ASTRAMIND_RUN_WINDOWS_WRAPPER_TESTS=1 for the Windows runtime proof",
)
def test_wrapper_launch_exception_is_atomic_redacted_and_has_hresult(tmp_path: Path) -> None:
    wrapper = _windows_path(Path("scripts/windows/run_realtime_market_task.ps1"))
    secret_key = "to" + "ken"
    local_app_data = tmp_path / "含 空格"
    local_app_data.mkdir()
    windows_local_app_data = _windows_path(local_app_data)
    script = f"""
$env:LOCALAPPDATA = '{_powershell_literal(windows_local_app_data)}'
. '{_powershell_literal(wrapper)}' `
    -Distro '测试 Ubuntu' `
    -Workdir '/home/ly/含 空格' `
    -MakeTarget 'realtime-market-service-run'
function Get-WslExecutablePath {{
    return 'C:\\definitely-missing-{secret_key}=private\\System32\\wsl.exe'
}}
Invoke-RealtimeMarketTask
"""

    completed = _run_powershell(script, check=False)
    status_path = local_app_data / "AstraMindOSMini/realtime-task-status.json"
    assert status_path.is_file(), (completed.returncode, completed.stdout, completed.stderr)
    diagnostic = parse_windows_wrapper_diagnostic(status_path.read_text(encoding="utf-8"))
    log = (local_app_data / "AstraMindOSMini/realtime-task.log").read_text(encoding="utf-8")

    assert completed.returncode == 127
    assert diagnostic.state == "wrapper_launch_exception"
    assert diagnostic.native_exit_code == 127
    assert diagnostic.exception_type is not None
    assert "FileNotFoundException" in diagnostic.exception_type
    assert diagnostic.exception_hresult is not None
    assert diagnostic.exception_hresult.startswith("0x")
    assert "private" not in (diagnostic.exception_message or "")
    assert "private" not in log
    assert "<redacted>" in log


def _windows_path(path: Path) -> str:
    return subprocess.run(
        ["wslpath", "-w", str(path)],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _powershell_literal(value: str) -> str:
    return value.replace("'", "''")


def _run_powershell(
    script: str,
    *,
    check: bool,
) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=15,
    )
    if check and completed.returncode != 0:
        raise subprocess.CalledProcessError(
            completed.returncode,
            completed.args,
            completed.stdout,
            completed.stderr,
        )
    return completed
