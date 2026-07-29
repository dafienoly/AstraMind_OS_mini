"""Preview and manage the local realtime market Windows scheduled task."""

from __future__ import annotations

import argparse
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from astramind_mini.local_ops.realtime_service_deployment import (
    TASK_NAME,
    TRIGGER_LABELS,
    RealtimeMarketTaskSpec,
    task_access_denied,
    task_is_present,
    task_xml,
)
from astramind_mini.local_ops.realtime_service_runtime import RealtimeStatusStore


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "action",
        choices=("preview", "install", "status", "start", "pause", "uninstall"),
    )
    parser.add_argument("--distro", default=os.environ.get("WSL_DISTRO_NAME"))
    parser.add_argument("--confirm-task-name")
    parser.add_argument("--confirm-workdir")
    return parser.parse_args()


def run(args: argparse.Namespace) -> int:
    if args.action == "status":
        return _status()
    if args.action in ("start", "pause", "uninstall"):
        return _mutate_existing(args.action)
    spec = _spec(args)
    artifact = _write_preview(spec)
    _print_preview(spec, artifact)
    if args.action == "preview":
        return 0
    _require_exact_confirmation(args, spec)
    completed = _task_command(["/Create", "/TN", TASK_NAME, "/XML", _windows_path(artifact), "/F"])
    if task_access_denied(completed.stdout, completed.stderr):
        completed = _elevated_install(artifact)
    verified = _task_command(["/Query", "/TN", TASK_NAME, "/FO", "LIST", "/V"])
    installed = task_is_present(verified.stdout, verified.stderr)
    _print_result("installed" if installed else "error", completed)
    if not installed:
        _print_scheduler_message(verified)
    return 0 if installed else 1


def _spec(args: argparse.Namespace) -> RealtimeMarketTaskSpec:
    if not args.distro:
        raise ValueError("无法识别 WSL 发行版，请提供 DISTRO")
    return RealtimeMarketTaskSpec(
        distro=str(args.distro),
        repository_root=Path.cwd().resolve(),
        windows_user_sid=_windows_user_sid(),
    )


def _windows_user_sid() -> str:
    command = "[System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value"
    completed = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", command],
        check=True,
        capture_output=True,
        text=True,
    )
    value = completed.stdout.strip()
    if not value.startswith("S-1-5-"):
        raise ValueError("无法确认 Windows 当前用户 SID")
    return value


def _write_preview(spec: RealtimeMarketTaskSpec) -> Path:
    path = Path("var/control/realtime-market-service/task.xml")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(task_xml(spec))
    return path


def _print_preview(spec: RealtimeMarketTaskSpec, artifact: Path) -> None:
    print(f"task_name={spec.task_name}")
    for label in TRIGGER_LABELS:
        print(f"trigger={label}")
    print("restart_on_failure=1m")
    print("multiple_instances=ignore_new")
    print(f"working_directory={spec.repository_root}")
    print("command=wsl.exe")
    print(f"arguments={spec.action_arguments}")
    print(f"task_xml={artifact}")
    print("broker_actions_allowed=false")


def _require_exact_confirmation(
    args: argparse.Namespace,
    spec: RealtimeMarketTaskSpec,
) -> None:
    if args.confirm_task_name != spec.task_name:
        raise ValueError("任务名称确认不匹配，拒绝安装")
    if args.confirm_workdir != spec.repository_root.as_posix():
        raise ValueError("工作目录确认不匹配，拒绝安装")


def _status() -> int:
    completed = _task_command(["/Query", "/TN", TASK_NAME, "/FO", "LIST", "/V"])
    installed = task_is_present(completed.stdout, completed.stderr)
    state = "installed" if installed else "not_installed"
    print(f"state={state}")
    print(f"task_name={TASK_NAME}")
    if installed:
        _print_scheduler_message(completed)
    runtime = RealtimeStatusStore(Path("var/control/realtime-market-service")).read()
    if runtime is None:
        print("runtime_state=unknown")
    else:
        age = max(
            0,
            int(
                (
                    datetime.now(UTC) - datetime.fromisoformat(runtime.updated_at).astimezone(UTC)
                ).total_seconds()
            ),
        )
        process_alive = Path(f"/proc/{runtime.pid}").is_dir()
        terminal = runtime.state in {"stopped", "error"}
        runtime_state = (
            runtime.state if terminal or (process_alive and age <= 90) else "stale_process"
        )
        print(f"runtime_state={runtime_state}")
        print(f"runtime_pid={runtime.pid}")
        print(f"runtime_heartbeat_age_seconds={age}")
        if runtime.market_date:
            print(f"runtime_market_date={runtime.market_date}")
        if runtime.session_id:
            print(f"runtime_session_id={runtime.session_id}")
        print(f"runtime_messages={runtime.messages}")
        print(f"runtime_microbatches={runtime.microbatches}")
        if runtime.last_error:
            print(f"runtime_last_error={runtime.last_error}")
    print("broker_actions_allowed=false")
    return 0


def _mutate_existing(action: str) -> int:
    if action == "start":
        completed = _task_command(["/Run", "/TN", TASK_NAME])
        state = "running" if completed.returncode == 0 else "error"
    else:
        _task_command(["/End", "/TN", TASK_NAME])
        command = (
            ["/Change", "/TN", TASK_NAME, "/Disable"]
            if action == "pause"
            else ["/Delete", "/TN", TASK_NAME, "/F"]
        )
        completed = _task_command(command)
        state = (
            "paused"
            if action == "pause" and completed.returncode == 0
            else "not_installed"
            if completed.returncode == 0
            else "error"
        )
    _print_result(state, completed)
    return completed.returncode


def _task_command(arguments: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["schtasks.exe", *arguments],
        check=False,
        capture_output=True,
        text=True,
        encoding="gbk",
        errors="replace",
    )


def _elevated_install(artifact: Path) -> subprocess.CompletedProcess[str]:
    helper = Path(__file__).with_name("manage_realtime_market_service_elevated.ps1")
    return subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            _windows_path(helper),
            "-TaskXml",
            _windows_path(artifact),
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="gbk",
        errors="replace",
    )


def _windows_path(path: Path) -> str:
    completed = subprocess.run(
        ["wslpath", "-w", str(path.resolve())],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _print_result(
    state: str,
    completed: subprocess.CompletedProcess[str],
) -> None:
    print(f"state={state}")
    _print_scheduler_message(completed)
    print(f"exit_code={completed.returncode}")
    print("broker_actions_allowed=false")


def _print_scheduler_message(
    completed: subprocess.CompletedProcess[str],
) -> None:
    message = (completed.stderr or completed.stdout).strip()
    if message:
        print("scheduler_message=" + " ".join(message.splitlines()))


def main() -> int:
    return run(parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
