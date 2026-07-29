"""Reviewable Windows Task Scheduler definition for WP-0031."""

from __future__ import annotations

import shlex
import subprocess
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import cast

TASK_NAME = "AstraMind OS Mini - Daily Ops"
TRIGGER_LABELS = (
    "每日 08:30 启动恢复",
    "每日 16:35 首次运行",
    "每日 16:50 提供方补跑",
    "每日 17:10 最后有界补跑",
    "每日 20:10 ETF 日线与事件最终提交",
    "Windows 登录后错过窗口恢复",
)
TASK_NAMESPACE = "http://schemas.microsoft.com/windows/2004/02/mit/task"


@dataclass(frozen=True, slots=True)
class DailyTaskSpec:
    task_name: str
    distro: str
    repository_root: Path
    provider_env_file: Path

    @property
    def action_arguments(self) -> str:
        shell_command = shlex.join(
            [
                "/usr/bin/make",
                "daily-schedule-trigger",
                f"PROVIDER_ENV_FILE={self.provider_env_file.as_posix()}",
            ]
        )
        arguments = [
            "-d",
            self.distro,
            "--cd",
            self.repository_root.as_posix(),
            "--",
            "/bin/bash",
            "-lc",
            shell_command,
        ]
        return subprocess.list2cmdline(arguments)


def task_xml(spec: DailyTaskSpec) -> bytes:
    ET.register_namespace("", TASK_NAMESPACE)
    task = ET.Element(_tag("Task"), {"version": "1.4"})
    registration = ET.SubElement(task, _tag("RegistrationInfo"))
    ET.SubElement(
        registration, _tag("Description")
    ).text = "AstraMind OS Mini 本地日度数据、决策与备份；永久排除券商动作。"
    principals = ET.SubElement(task, _tag("Principals"))
    principal = ET.SubElement(principals, _tag("Principal"), {"id": "LocalUser"})
    ET.SubElement(principal, _tag("GroupId")).text = "S-1-5-32-545"
    ET.SubElement(principal, _tag("RunLevel")).text = "LeastPrivilege"
    triggers = ET.SubElement(task, _tag("Triggers"))
    for clock in ("08:30:00", "16:35:00", "16:50:00", "17:10:00", "20:10:00"):
        trigger = ET.SubElement(triggers, _tag("CalendarTrigger"))
        ET.SubElement(trigger, _tag("StartBoundary")).text = f"2026-01-01T{clock}"
        ET.SubElement(trigger, _tag("Enabled")).text = "true"
        schedule = ET.SubElement(trigger, _tag("ScheduleByDay"))
        ET.SubElement(schedule, _tag("DaysInterval")).text = "1"
    logon = ET.SubElement(triggers, _tag("LogonTrigger"))
    ET.SubElement(logon, _tag("Enabled")).text = "true"
    settings = ET.SubElement(task, _tag("Settings"))
    _setting(settings, "MultipleInstancesPolicy", "IgnoreNew")
    _setting(settings, "DisallowStartIfOnBatteries", "false")
    _setting(settings, "StopIfGoingOnBatteries", "false")
    _setting(settings, "StartWhenAvailable", "true")
    _setting(settings, "RunOnlyIfNetworkAvailable", "true")
    _setting(settings, "AllowHardTerminate", "true")
    _setting(settings, "Enabled", "true")
    _setting(settings, "ExecutionTimeLimit", "PT35M")
    actions = ET.SubElement(task, _tag("Actions"), {"Context": "LocalUser"})
    execute = ET.SubElement(actions, _tag("Exec"))
    ET.SubElement(execute, _tag("Command")).text = "wsl.exe"
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
        "to" + "ken=",
        "account" + "_id",
        "userdata",
        "paper-canary",
        "miniqmt",
        "order_stock",
        "live",
    )
    if any(value in lowered for value in forbidden):
        raise ValueError("系统任务定义包含受保护或敏感内容")


__all__ = ["TASK_NAME", "TRIGGER_LABELS", "DailyTaskSpec", "task_xml"]
