"""Reviewable Windows Task Scheduler definition for realtime market data."""

from __future__ import annotations

import shlex
import subprocess
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

TASK_NAME = "AstraMind OS Mini - Realtime Market"
TASK_NAMESPACE = "http://schemas.microsoft.com/windows/2004/02/mit/task"
TRIGGER_LABELS = ("Windows 登录后启动", "每日 08:55 恢复启动")
WINDOWS_WRAPPER_FILENAME = "run_realtime_market_task-v1.ps1"
WINDOWS_POWERSHELL_EXECUTABLE = (
    r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"
)
type SchedulerQueryState = Literal["installed", "not_installed", "query_failed"]


@dataclass(frozen=True, slots=True)
class RealtimeMarketTaskSpec:
    distro: str
    repository_root: Path
    windows_user_sid: str
    windows_local_app_data: str
    task_name: str = TASK_NAME

    @property
    def action_arguments(self) -> str:
        shell_command = shlex.join(
            [
                "/usr/bin/uv",
                "run",
                "python",
                "scripts/manage_realtime_market_service.py",
                "run-task",
                "--make-target",
                "realtime-market-service-run",
            ]
        )
        return subprocess.list2cmdline(
            [
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                self.wrapper_path,
                "-Distro",
                self.distro,
                "-Workdir",
                self.repository_root.as_posix(),
                "-Command",
                shell_command,
            ]
        )

    @property
    def wrapper_path(self) -> str:
        root = self.windows_local_app_data.rstrip("\\/")
        return rf"{root}\AstraMindOSMini\{WINDOWS_WRAPPER_FILENAME}"


def task_xml(spec: RealtimeMarketTaskSpec) -> bytes:
    ET.register_namespace("", TASK_NAMESPACE)
    task = ET.Element(_tag("Task"), {"version": "1.4"})
    registration = ET.SubElement(task, _tag("RegistrationInfo"))
    ET.SubElement(
        registration, _tag("Description")
    ).text = "AstraMind OS Mini 全市场只读实时行情；永久排除账户与券商动作。"
    principals = ET.SubElement(task, _tag("Principals"))
    principal = ET.SubElement(principals, _tag("Principal"), {"id": "LocalUser"})
    ET.SubElement(principal, _tag("UserId")).text = spec.windows_user_sid
    ET.SubElement(principal, _tag("LogonType")).text = "InteractiveToken"
    ET.SubElement(principal, _tag("RunLevel")).text = "LeastPrivilege"
    triggers = ET.SubElement(task, _tag("Triggers"))
    logon = ET.SubElement(triggers, _tag("LogonTrigger"))
    ET.SubElement(logon, _tag("Enabled")).text = "true"
    daily = ET.SubElement(triggers, _tag("CalendarTrigger"))
    ET.SubElement(daily, _tag("StartBoundary")).text = "2026-01-01T08:55:00"
    ET.SubElement(daily, _tag("Enabled")).text = "true"
    schedule = ET.SubElement(daily, _tag("ScheduleByDay"))
    ET.SubElement(schedule, _tag("DaysInterval")).text = "1"
    settings = ET.SubElement(task, _tag("Settings"))
    _setting(settings, "MultipleInstancesPolicy", "IgnoreNew")
    _setting(settings, "DisallowStartIfOnBatteries", "false")
    _setting(settings, "StopIfGoingOnBatteries", "false")
    _setting(settings, "StartWhenAvailable", "true")
    _setting(settings, "RunOnlyIfNetworkAvailable", "false")
    _setting(settings, "AllowHardTerminate", "true")
    _setting(settings, "Enabled", "true")
    _setting(settings, "ExecutionTimeLimit", "PT0S")
    restart = ET.SubElement(settings, _tag("RestartOnFailure"))
    _setting(restart, "Interval", "PT1M")
    _setting(restart, "Count", "999")
    actions = ET.SubElement(task, _tag("Actions"), {"Context": "LocalUser"})
    execute = ET.SubElement(actions, _tag("Exec"))
    ET.SubElement(execute, _tag("Command")).text = WINDOWS_POWERSHELL_EXECUTABLE
    ET.SubElement(execute, _tag("Arguments")).text = spec.action_arguments
    payload = cast(bytes, ET.tostring(task, encoding="utf-16", xml_declaration=True))
    _assert_safe(payload.decode("utf-16"))
    return payload


def _setting(parent: ET.Element, name: str, value: str) -> None:
    ET.SubElement(parent, _tag(name)).text = value


def _tag(name: str) -> str:
    return f"{{{TASK_NAMESPACE}}}{name}"


def _assert_safe(payload: str) -> None:
    lowered = payload.lower()
    forbidden = (
        "account" + "_id",
        "userdata",
        "paper-canary",
        "order_stock",
        "cancel_order",
        "trader",
        "live-order",
    )
    if any(value in lowered for value in forbidden):
        raise ValueError("实时行情任务定义包含账户、交易或敏感内容")


def task_access_denied(stdout: str, stderr: str) -> bool:
    message = (stderr or stdout).lower()
    return "拒绝访问" in message or "access is denied" in message


def task_is_present(stdout: str, stderr: str) -> bool:
    return TASK_NAME.lower() in "\n".join((stdout, stderr)).lower()


def scheduler_query_state(
    returncode: int,
    stdout: str,
    stderr: str,
) -> SchedulerQueryState:
    if returncode == 0 and task_is_present(stdout, stderr):
        return "installed"
    message = "\n".join((stdout, stderr)).casefold()
    missing_markers = (
        "cannot find the file specified",
        "找不到指定的文件",
        "系统找不到指定的文件",
    )
    if returncode == 1 and any(marker in message for marker in missing_markers):
        return "not_installed"
    return "query_failed"


__all__ = [
    "TASK_NAME",
    "TRIGGER_LABELS",
    "WINDOWS_POWERSHELL_EXECUTABLE",
    "WINDOWS_WRAPPER_FILENAME",
    "RealtimeMarketTaskSpec",
    "SchedulerQueryState",
    "scheduler_query_state",
    "task_access_denied",
    "task_is_present",
    "task_xml",
]
