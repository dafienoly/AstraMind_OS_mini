import argparse
import re
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
from astramind_mini.local_ops.realtime_windows_wrapper import install_windows_wrapper
from scripts.manage_realtime_market_service import (
    _append_bounded_log,
    _mutate_existing,
    _run_task,
    _status,
    _task_command,
    run,
)


def test_realtime_task_is_persistent_restartable_and_broker_free() -> None:
    spec = RealtimeMarketTaskSpec(
        distro="Ubuntu",
        repository_root=Path("/home/ly/work/AstraMind_OS_mini"),
        windows_user_sid="S-1-5-21-1-2-3-1001",
        windows_local_app_data=r"C:\Users\tester\AppData\Local",
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
    assert "run_realtime_market_task-v1.ps1" in payload
    assert "wsl.exe" not in payload
    assert "wsl.localhost" not in payload.lower()
    assert r"C:\Users\tester\AppData\Local\AstraMindOSMini" in payload
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
    assert "Write-BoundedLog" in payload
    assert "Rotate-Log $PayloadBytes" in payload
    assert "Limit-LogFile $LogPath" in payload
    assert "$MaxLineCharacters = 131072" in payload
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


def test_windows_wrapper_redacts_quoted_multiword_values_without_eating_paths() -> None:
    payload = Path("scripts/windows/run_realtime_market_task.ps1").read_text(encoding="utf-8")
    pattern = payload.split("$Pattern = @'", 1)[1].split("'@", 1)[0].strip()
    compatible_pattern = pattern.replace("(?<prefix>", "(?P<prefix>")
    compiled = re.compile(compatible_pattern)
    key_a = "to" + "ken"
    key_b = "sec" + "ret"
    fixture = f"{key_a}=\"alpha beta gamma\", {key_b}='two word secret'; /secret/path remains"

    redacted = compiled.sub(
        lambda match: f"{match.group('prefix')}<redacted>",
        fixture,
    )

    assert "alpha beta gamma" not in redacted
    assert "two word secret" not in redacted
    assert "/secret/path remains" in redacted


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


def test_wrapper_install_is_atomic_and_hash_verified(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spec = RealtimeMarketTaskSpec(
        distro="Ubuntu",
        repository_root=Path("/workspace"),
        windows_user_sid="S-1-5-21-1",
        windows_local_app_data=r"C:\Users\tester\AppData\Local",
    )
    captured: list[list[str]] = []

    def command(arguments: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        captured.append(arguments)
        return subprocess.CompletedProcess(arguments, 0, "wrapper_hash=ABC", "")

    monkeypatch.setattr(
        "astramind_mini.local_ops.realtime_windows_wrapper._windows_path",
        lambda _: r"\\wsl.localhost\Ubuntu\workspace\scripts\windows\wrapper.ps1",
    )
    monkeypatch.setattr(subprocess, "run", command)

    assert install_windows_wrapper(spec).returncode == 0
    invocation = captured[0]
    script = invocation[invocation.index("-Command") + 1]
    assert "Copy-Item" in script
    assert "Copy-Item -LiteralPath $Source -Destination $Temporary -Force" in script
    assert "Get-FileHash -Algorithm SHA256" in script
    assert "Move-Item -LiteralPath $Temporary -Destination $Target -Force" in script
    assert script.index("Copy-Item") < script.index("Move-Item")
    assert invocation[-1] == spec.wrapper_path


def test_install_copies_wrapper_before_registration_and_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spec = RealtimeMarketTaskSpec(
        distro="Ubuntu",
        repository_root=tmp_path,
        windows_user_sid="S-1-5-21-1",
        windows_local_app_data=r"C:\Users\tester\AppData\Local",
    )
    args = argparse.Namespace(
        action="install",
        distro="Ubuntu",
        confirm_task_name=TASK_NAME,
        confirm_workdir=tmp_path.as_posix(),
        make_target="realtime-market-service-run",
    )
    events: list[str] = []
    artifact = tmp_path / "task.xml"
    artifact.write_bytes(task_xml(spec))
    monkeypatch.setattr("scripts.manage_realtime_market_service._spec", lambda _: spec)
    monkeypatch.setattr("scripts.manage_realtime_market_service._write_preview", lambda _: artifact)
    monkeypatch.setattr("scripts.manage_realtime_market_service._print_preview", lambda *_: None)
    monkeypatch.setattr(
        "scripts.manage_realtime_market_service._windows_path", lambda _: r"C:\task.xml"
    )

    preview_args = argparse.Namespace(**vars(args))
    preview_args.action = "preview"
    monkeypatch.setattr(
        "scripts.manage_realtime_market_service._install_windows_wrapper",
        lambda _: (_ for _ in ()).throw(AssertionError("preview copied wrapper")),
    )
    assert run(preview_args) == 0

    def failed_copy(_: RealtimeMarketTaskSpec) -> subprocess.CompletedProcess[str]:
        events.append("copy")
        return subprocess.CompletedProcess([], 9, "", "copy failed")

    def task_command(_: list[str]) -> subprocess.CompletedProcess[str]:
        events.append("register")
        return subprocess.CompletedProcess([], 0, "", "")

    monkeypatch.setattr(
        "scripts.manage_realtime_market_service._install_windows_wrapper", failed_copy
    )
    monkeypatch.setattr("scripts.manage_realtime_market_service._task_command", task_command)
    assert run(args) == 9
    assert events == ["copy"]

    events.clear()

    def successful_copy(_: RealtimeMarketTaskSpec) -> subprocess.CompletedProcess[str]:
        events.append("copy")
        return subprocess.CompletedProcess([], 0, "wrapper_hash=ABC", "")

    def successful_task(arguments: list[str]) -> subprocess.CompletedProcess[str]:
        events.append("register" if "/Create" in arguments else "verify")
        output = f"任务名: \\{TASK_NAME}" if "/Query" in arguments else ""
        return subprocess.CompletedProcess(arguments, 0, output, "")

    monkeypatch.setattr(
        "scripts.manage_realtime_market_service._install_windows_wrapper",
        successful_copy,
    )
    monkeypatch.setattr("scripts.manage_realtime_market_service._task_command", successful_task)
    assert run(args) == 0
    assert events == ["copy", "register", "verify"]


def test_windows_wrapper_caps_every_line_before_four_generation_rotation() -> None:
    payload = Path("scripts/windows/run_realtime_market_task.ps1").read_text(encoding="utf-8")
    max_chars = int(re.search(r"\$MaxLineCharacters = (\d+)", payload).group(1))  # type: ignore[union-attr]

    assert max_chars * 4 + len("<truncated>\r\n") < 2 * 1024 * 1024
    assert "$SafeValue.Substring(0, $MaxLineCharacters)" in payload
    assert "Rotate-Log $PayloadBytes" in payload
    assert "[System.IO.File]::AppendAllText" in payload
    assert payload.index("Rotate-Log $PayloadBytes") < payload.index(
        "[System.IO.File]::AppendAllText"
    )
    assert payload.index("[System.IO.File]::AppendAllText") < payload.index(
        "Limit-LogFile $LogPath", payload.index("[System.IO.File]::AppendAllText")
    )
    assert 'Remove-Item "$LogPath.$Generations"' in payload
    assert "$Generations = 4" in payload
