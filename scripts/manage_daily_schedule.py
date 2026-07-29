"""Preview and manage the reviewable WP-0031 Windows scheduled task."""

from __future__ import annotations

import argparse
import os
import subprocess
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from astramind_mini.config import Settings
from astramind_mini.local_ops.daily_schedule_deployment import (
    TASK_NAME,
    TRIGGER_LABELS,
    DailyTaskSpec,
    task_xml,
)
from astramind_mini.local_ops.daily_scheduler_contracts import DailyScheduleDeployment
from astramind_mini.local_ops.daily_scheduler_store import DailySchedulerStore
from astramind_mini.local_ops.identity import operations_hash

SHANGHAI = ZoneInfo("Asia/Shanghai")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "action",
        choices=("preview", "install", "status", "pause", "uninstall"),
    )
    parser.add_argument("--provider-env-file", type=Path)
    parser.add_argument("--distro", default=os.environ.get("WSL_DISTRO_NAME"))
    parser.add_argument("--confirm-task-name")
    parser.add_argument("--confirm-workdir")
    return parser.parse_args()


def run(args: argparse.Namespace) -> int:
    settings = Settings()
    store = DailySchedulerStore(settings.local_ops_db_path)
    if args.action == "status":
        return _status(store)
    if args.action in ("pause", "uninstall"):
        return _mutate_existing(args.action, store)
    spec = _spec(args)
    artifact = _write_preview(spec)
    _print_preview(spec, artifact)
    if args.action == "preview":
        if store.deployment() is None:
            _record(store, "not_installed", "preview_generated")
        return 0
    _require_exact_confirmation(args, spec)
    completed = _install_task(spec, artifact)
    state = "installed" if completed.returncode == 0 else "error"
    _record(store, state, f"install_exit_{completed.returncode}")
    _print_scheduler_diagnostic(completed)
    print(f"install_state={state}")
    print(f"exit_code={completed.returncode}")
    print("broker_actions_allowed=false")
    return completed.returncode


def _spec(args: argparse.Namespace) -> DailyTaskSpec:
    if args.provider_env_file is None or not args.provider_env_file.is_absolute():
        raise ValueError("预览或安装必须提供绝对 PROVIDER_ENV_FILE")
    if not args.distro:
        raise ValueError("无法识别 WSL 发行版，请提供 DISTRO")
    return DailyTaskSpec(
        task_name=TASK_NAME,
        distro=str(args.distro),
        repository_root=Path.cwd().resolve(),
        provider_env_file=args.provider_env_file,
    )


def _write_preview(spec: DailyTaskSpec) -> Path:
    path = Path("var/control/daily-scheduler/task.xml")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(task_xml(spec))
    return path


def _print_preview(spec: DailyTaskSpec, artifact: Path) -> None:
    print(f"task_name={spec.task_name}")
    for label in TRIGGER_LABELS:
        print(f"trigger={label}")
    print(f"working_directory={spec.repository_root}")
    print(f"provider_environment_source={spec.provider_env_file}")
    print("command=wsl.exe")
    print(f"arguments={spec.action_arguments}")
    print(f"task_xml={artifact}")
    print("broker_actions_allowed=false")


def _require_exact_confirmation(args: argparse.Namespace, spec: DailyTaskSpec) -> None:
    if args.confirm_task_name != spec.task_name:
        raise ValueError("任务名称确认不匹配，拒绝安装")
    if args.confirm_workdir != spec.repository_root.as_posix():
        raise ValueError("工作目录确认不匹配，拒绝安装")


def _status(store: DailySchedulerStore) -> int:
    installed = _task_exists()
    current = store.deployment()
    if installed:
        _record(store, "installed", "query_confirmed")
        state = "installed"
    else:
        state = (
            "not_installed" if current is None or current.state == "installed" else current.state
        )
    print(f"state={state}")
    print(f"task_name={TASK_NAME}")
    print("broker_actions_allowed=false")
    return 0


def _mutate_existing(action: str, store: DailySchedulerStore) -> int:
    command = (
        ["schtasks.exe", "/Change", "/TN", TASK_NAME, "/Disable"]
        if action == "pause"
        else ["schtasks.exe", "/Delete", "/TN", TASK_NAME, "/F"]
    )
    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        encoding="gbk",
        errors="replace",
    )
    state = "paused" if action == "pause" and completed.returncode == 0 else "not_installed"
    if completed.returncode != 0:
        state = "error"
    _record(store, state, f"{action}_exit_{completed.returncode}")
    print(f"state={state}")
    print("broker_actions_allowed=false")
    return completed.returncode


def _task_exists() -> bool:
    completed = subprocess.run(
        ["schtasks.exe", "/Query", "/TN", TASK_NAME],
        check=False,
        capture_output=True,
        text=True,
        encoding="gbk",
        errors="replace",
    )
    return completed.returncode == 0


def _windows_path(path: Path) -> str:
    completed = subprocess.run(
        ["wslpath", "-w", str(path.resolve())],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _install_task(
    spec: DailyTaskSpec,
    artifact: Path,
) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        [
            "schtasks.exe",
            "/Create",
            "/TN",
            spec.task_name,
            "/XML",
            _windows_path(artifact),
            "/F",
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="gbk",
        errors="replace",
    )
    message = (completed.stderr or completed.stdout).lower()
    access_denied = "拒绝访问" in message or "access is denied" in message
    if completed.returncode == 0 or not access_denied:
        return completed
    helper = Path(__file__).with_name("manage_daily_schedule_elevated.ps1")
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


def _print_scheduler_diagnostic(completed: subprocess.CompletedProcess[str]) -> None:
    message = (completed.stderr or completed.stdout).strip()
    if message:
        print("scheduler_message=" + " ".join(message.splitlines()))


def _record(
    store: DailySchedulerStore,
    state: str,
    result: str,
) -> None:
    now = datetime.now(SHANGHAI)
    decision = store.latest_decision()
    identity = {
        "state": state,
        "task_name": TASK_NAME,
        "trigger_labels": TRIGGER_LABELS,
        "next_run_at": decision.next_trigger_at if decision else None,
        "last_result": result,
        "updated_at": now,
        "broker_actions_allowed": False,
    }
    digest = operations_hash(identity)
    store.publish_deployment(
        DailyScheduleDeployment.model_validate({**identity, "content_hash": digest})
    )


def main() -> int:
    return run(parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
