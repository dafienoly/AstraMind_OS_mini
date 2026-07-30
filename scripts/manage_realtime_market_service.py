"""Preview and manage the local realtime market Windows scheduled task."""

from __future__ import annotations

import argparse
import os
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

from astramind_mini.local_ops.realtime_service_deployment import (
    TASK_NAME,
    TRIGGER_LABELS,
    WINDOWS_POWERSHELL_EXECUTABLE,
    RealtimeMarketTaskSpec,
    task_access_denied,
    task_xml,
)
from astramind_mini.local_ops.realtime_service_diagnostics import realtime_status_lines
from astramind_mini.local_ops.realtime_service_runner import (
    run_realtime_task,
)
from astramind_mini.local_ops.realtime_windows_wrapper import (
    install_windows_wrapper as _install_windows_wrapper,
)
from astramind_mini.local_ops.realtime_windows_wrapper import (
    windows_local_app_data as _windows_local_app_data,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "action",
        choices=("preview", "install", "status", "start", "pause", "uninstall", "run-task"),
    )
    parser.add_argument("--distro", default=os.environ.get("WSL_DISTRO_NAME"))
    parser.add_argument("--confirm-task-name")
    parser.add_argument("--confirm-workdir")
    parser.add_argument("--make-target", default="realtime-market-service-run")
    return parser.parse_args()


def run(args: argparse.Namespace) -> int:
    if args.action == "run-task":
        return run_realtime_task(args.make_target)
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
    wrapper_install = _install_windows_wrapper(spec)
    if wrapper_install.returncode != 0:
        _print_result("wrapper_install_failed", wrapper_install)
        return wrapper_install.returncode
    completed = _task_command(["/Create", "/TN", TASK_NAME, "/XML", _windows_path(artifact), "/F"])
    if task_access_denied(completed.stdout, completed.stderr):
        completed = _elevated_install(artifact)
    if completed.returncode != 0:
        _print_result("registration_failed", completed)
        return completed.returncode
    verified = _task_command(["/Query", "/TN", TASK_NAME, "/XML"])
    installed = verified.returncode == 0 and _task_definition_matches(verified.stdout, spec)
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
        windows_local_app_data=_windows_local_app_data(),
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
    print(f"command={WINDOWS_POWERSHELL_EXECUTABLE}")
    print(f"arguments={spec.action_arguments}")
    print(f"windows_wrapper={spec.wrapper_path}")
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
    for line in realtime_status_lines(completed):
        print(line)
    return 0


def _mutate_existing(action: str) -> int:
    if action == "start":
        enabled = _task_command(["/Change", "/TN", TASK_NAME, "/Enable"])
        if enabled.returncode != 0:
            _print_result("error", enabled)
            return enabled.returncode
        completed = _task_command(["/Run", "/TN", TASK_NAME])
        state = "running" if completed.returncode == 0 else "error"
    else:
        ended = _task_command(["/End", "/TN", TASK_NAME])
        if action == "pause" and ended.returncode != 0:
            _print_result("error", ended)
            return ended.returncode
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
    try:
        return subprocess.run(
            ["schtasks.exe", *arguments],
            check=False,
            capture_output=True,
            text=True,
            encoding="gbk",
            errors="replace",
        )
    except OSError as error:
        return subprocess.CompletedProcess(
            ["schtasks.exe", *arguments],
            127,
            "",
            f"scheduler_query_start_failed:{type(error).__name__}",
        )


def _task_definition_matches(payload: str, spec: RealtimeMarketTaskSpec) -> bool:
    task_start = payload.find("<Task")
    if task_start < 0:
        return False
    try:
        root = ET.fromstring(payload[task_start:])
    except ET.ParseError:
        return False
    command = root.findtext(f".//{{{root.tag.partition('}')[0].lstrip('{')}}}Command")
    arguments = root.findtext(f".//{{{root.tag.partition('}')[0].lstrip('{')}}}Arguments")
    return command == WINDOWS_POWERSHELL_EXECUTABLE and arguments == spec.action_arguments


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
