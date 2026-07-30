import subprocess
from io import BytesIO
from pathlib import Path

import pytest

from astramind_mini.local_ops.realtime_service_deployment import (
    TASK_NAME,
    RealtimeMarketTaskSpec,
    scheduler_query_state,
    task_access_denied,
    task_is_present,
    task_xml,
)
from scripts.manage_realtime_market_service import (
    _append_bounded_log,
    _mutate_existing,
    _run_task,
    _status,
    _task_command,
)


def test_realtime_task_is_persistent_restartable_and_broker_free() -> None:
    spec = RealtimeMarketTaskSpec(
        distro="Ubuntu",
        repository_root=Path("/home/ly/work/AstraMind_OS_mini"),
        windows_user_sid="S-1-5-21-1-2-3-1001",
    )

    payload = task_xml(spec).decode("utf-16")

    assert TASK_NAME == "AstraMind OS Mini - Realtime Market"
    assert payload.count("LogonTrigger") == 2
    assert payload.count("CalendarTrigger") == 2
    assert "2026-01-01T08:55:00" in payload
    assert "RestartOnFailure" in payload
    assert "PT1M" in payload
    assert "IgnoreNew" in payload
    assert "PT0S" in payload
    assert "realtime-market-service-run" in payload
    assert "/home/ly/work/AstraMind_OS_mini" in payload
    assert "powershell.exe" in payload
    assert "run_realtime_market_task.ps1" in payload
    assert "wsl.exe" not in payload
    assert all(
        forbidden not in payload.lower()
        for forbidden in (
            "account" + "_id",
            "paper-canary",
            "order_stock",
            "cancel_order",
        )
    )


def test_scheduler_result_does_not_trust_wsl_exit_code_alone() -> None:
    assert task_access_denied("错误: 拒绝访问。", "")
    assert task_access_denied("", "ERROR: Access is denied.")
    assert not task_is_present("错误: 拒绝访问。", "")
    assert task_is_present(
        f"任务名: \\{TASK_NAME}\n状态: Ready",
        "",
    )


def test_windows_task_wrapper_bounds_logs_and_exposes_wsl_exit() -> None:
    payload = Path("scripts/windows/run_realtime_market_task.ps1").read_text(encoding="utf-8")

    assert "$MaxBytes = 2MB" in payload
    assert "$Generations = 4" in payload
    assert "wsl_start_failed=" in payload
    assert "wsl_exit_code=" in payload
    assert "Redact-Line" in payload
    assert "token|api[_ -]?key|secret|password|account" in payload
    assert scheduler_query_state(0, f"任务名: \\{TASK_NAME}", "") == "installed"
    assert (
        scheduler_query_state(1, "", "ERROR: The system cannot find the file specified.")
        == "not_installed"
    )
    assert scheduler_query_state(1, "", "ERROR: Access is denied.") == "query_failed"
    assert scheduler_query_state(255, "", "WSL interop failure") == "query_failed"
    assert (
        scheduler_query_state(1, f"ERROR while querying {TASK_NAME}", "Access is denied")
        == "query_failed"
    )


def test_task_log_is_rotated_and_bounded_while_process_is_running(tmp_path: Path) -> None:
    path = tmp_path / "service.log"
    _append_bounded_log(path, b"12345678", max_bytes=10)
    _append_bounded_log(path, b"abcdefgh", max_bytes=10)

    assert path.read_bytes() == b"abcdefgh"
    assert path.with_name("service.log.1").read_bytes() == b"12345678"


def test_scheduler_spawn_failure_is_query_failed_and_preserves_last_fact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    fact = tmp_path / "var/control/realtime-market-service/scheduler-fact.json"
    fact.parent.mkdir(parents=True)
    fact.write_text(
        '{"state":"installed","checked_at":"2026-07-30T01:00:00+00:00"}',
        encoding="utf-8",
    )
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("private windows detail")),
    )

    assert _task_command(["/Query"]).returncode == 127
    assert _status() == 0
    output = capsys.readouterr().out
    assert "state=query_failed" in output
    assert "last_known_installed=true" in output
    assert "private windows detail" not in output


def test_runner_start_and_nonzero_exit_are_blocked_with_log(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        subprocess,
        "Popen",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("cannot execute")),
    )

    assert _run_task("realtime-market-service-run") == 127
    assert (tmp_path / "var/control/realtime-market-service/service.log").is_file()
    status = (tmp_path / "var/control/realtime-market-service/status.json").read_text()
    assert '"state": "blocked"' in status
    assert "cannot execute" not in status

    class FailedProcess:
        stdout = BytesIO(b"")

        @staticmethod
        def wait() -> int:
            return 9

    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: FailedProcess())
    assert _run_task("realtime-market-service-run") == 9
    status = (tmp_path / "var/control/realtime-market-service/status.json").read_text()
    assert '"state": "blocked"' in status
    assert '"exit_code": 9' in status


def test_pause_fails_when_end_did_not_succeed(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []

    def command(arguments: list[str]) -> subprocess.CompletedProcess[str]:
        calls.append(arguments)
        return subprocess.CompletedProcess(arguments, 5, "", "end failed")

    monkeypatch.setattr("scripts.manage_realtime_market_service._task_command", command)

    assert _mutate_existing("pause") == 5
    assert calls == [["/End", "/TN", TASK_NAME]]
