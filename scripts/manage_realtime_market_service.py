"""Preview and manage the local realtime market Windows scheduled task."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from astramind_mini.local_ops.realtime_service_deployment import (
    TASK_NAME,
    TRIGGER_LABELS,
    RealtimeMarketTaskSpec,
    scheduler_query_state,
    task_access_denied,
    task_xml,
)
from astramind_mini.local_ops.realtime_service_runtime import RealtimeStatusStore


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
        return _run_task(args.make_target)
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
    installed = (
        scheduler_query_state(verified.returncode, verified.stdout, verified.stderr) == "installed"
    )
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
    state = scheduler_query_state(completed.returncode, completed.stdout, completed.stderr)
    installed = state == "installed"
    control_root = Path("var/control/realtime-market-service")
    fact_path = control_root / "scheduler-fact.json"
    previous = _read_scheduler_fact(fact_path)
    if state != "query_failed":
        _write_scheduler_fact(fact_path, state)
    print(f"state={state}")
    print(f"task_name={TASK_NAME}")
    if state == "query_failed" and previous is not None:
        print(f"last_known_task_state={previous['state']}")
        print(f"last_known_installed={str(previous['state'] == 'installed').lower()}")
        print(f"last_known_task_checked_at={previous['checked_at']}")
    if installed or state == "query_failed":
        _print_scheduler_message(completed)
    print(f"scheduler_exit_code={completed.returncode}")
    runtime = RealtimeStatusStore(control_root).read()
    if runtime is None:
        print("wsl_process_state=not_running")
        print("feed_session_state=not_started")
        print("projection_state=not_available")
        print("completed_day_state=unknown")
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
        terminal = runtime.process_state == "exited" or runtime.state in {
            "stopped",
            "error",
            "blocked",
            "reconciled",
        }
        runtime_state = (
            runtime.state if terminal or (process_alive and age <= 90) else "stale_process"
        )
        print(f"wsl_process_state={runtime_state}")
        print(f"feed_session_state={runtime.feed_state}")
        print(f"projection_state={runtime.projection_state}")
        print(f"completed_day_state={runtime.completed_day_state}")
        print(f"runtime_pid={runtime.pid}")
        print(f"runtime_heartbeat_age_seconds={age}")
        if runtime.market_date:
            print(f"runtime_market_date={runtime.market_date}")
        if runtime.session_id:
            print(f"runtime_session_id={runtime.session_id}")
        print(f"runtime_messages={runtime.messages}")
        print(f"runtime_microbatches={runtime.microbatches}")
        if runtime.last_successful_heartbeat_at:
            print(f"runtime_last_successful_heartbeat={runtime.last_successful_heartbeat_at}")
        if runtime.last_message_at:
            print(f"runtime_last_message_at={runtime.last_message_at}")
        if runtime.last_microbatch_at:
            print(f"runtime_last_microbatch_at={runtime.last_microbatch_at}")
        if runtime.exit_code is not None:
            print(f"runtime_exit_code={runtime.exit_code}")
        if runtime.last_error:
            print(f"runtime_last_error={runtime.last_error}")
        for index, failure in enumerate(runtime.retry_failures, start=1):
            print(f"retry_failure_{index}={json.dumps(failure, ensure_ascii=False)}")
        if runtime.log_path:
            print(f"runtime_log_path={runtime.log_path}")
        if runtime.recovery_action:
            print(f"runtime_recovery_action={runtime.recovery_action}")
    print("broker_actions_allowed=false")
    return 0


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


def _mutate_existing(action: str) -> int:
    if action == "start":
        enabled = _task_command(["/Change", "/TN", TASK_NAME, "/Enable"])
        if enabled.returncode != 0:
            _print_result("error", enabled)
            return enabled.returncode
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


def _run_task(make_target: str) -> int:
    if make_target != "realtime-market-service-run":
        raise ValueError("拒绝未知实时服务目标")
    log_root = Path("var/control/realtime-market-service")
    log_root.mkdir(parents=True, exist_ok=True)
    log_path = log_root / "service.log"
    process = subprocess.Popen(
        ["/usr/bin/make", make_target],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    assert process.stdout is not None
    while chunk := process.stdout.read(64 * 1024):
        _append_bounded_log(log_path, chunk)
    returncode = process.wait()
    status_store = RealtimeStatusStore(log_root)
    current = status_store.read()
    terminal_state = (
        current.state if current is not None else ("stopped" if returncode == 0 else "blocked")
    )
    status_store.publish(
        terminal_state,
        process_state="exited",
        feed_state=current.feed_state if current is not None else "not_started",
        projection_state=current.projection_state if current is not None else "unknown",
        completed_day_state=current.completed_day_state if current is not None else "unknown",
        exit_code=returncode,
        last_error=current.last_error if current is not None else None,
        retry_failures=current.retry_failures if current is not None else (),
        recovery_action=current.recovery_action if current is not None else None,
        successful_heartbeat=False,
    )
    return returncode


def _rotate_logs(path: Path, *, generations: int = 4, max_bytes: int = 2_000_000) -> None:
    if not path.is_file() or path.stat().st_size < max_bytes:
        return
    path.with_name(f"{path.name}.{generations}").unlink(missing_ok=True)
    for index in range(generations - 1, 0, -1):
        source = path.with_name(f"{path.name}.{index}")
        if source.is_file():
            os.replace(source, path.with_name(f"{path.name}.{index + 1}"))
    os.replace(path, path.with_name(f"{path.name}.1"))


def _truncate_log(path: Path, *, max_bytes: int = 2_000_000) -> None:
    if path.stat().st_size <= max_bytes:
        return
    with path.open("rb") as stream:
        stream.seek(-max_bytes, os.SEEK_END)
        tail = stream.read()
    temporary = path.with_suffix(".tmp")
    temporary.write_bytes(tail)
    os.replace(temporary, path)


def _append_bounded_log(path: Path, payload: bytes, *, max_bytes: int = 2_000_000) -> None:
    if path.is_file() and path.stat().st_size + len(payload) > max_bytes:
        _rotate_logs(path, max_bytes=0)
    with path.open("ab", buffering=0) as stream:
        stream.write(payload[-max_bytes:])
    _truncate_log(path, max_bytes=max_bytes)


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
