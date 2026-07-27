"""Diagnose the local development environment without requiring project dependencies."""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import socket
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Check:
    name: str
    level: str
    detail: str
    remedy: str | None = None


def command_version(command: str, *args: str) -> str | None:
    executable = shutil.which(command)
    if executable is None:
        return None
    result = subprocess.run(
        [executable, *args],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    output = (result.stdout or result.stderr).strip().splitlines()
    return output[0] if result.returncode == 0 and output else None


def port_available(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.2)
        return probe.connect_ex(("127.0.0.1", port)) != 0


def project_python_probe() -> tuple[bool, str]:
    python = ROOT / ".venv/bin/python"
    if not python.exists():
        return False, "项目虚拟环境不存在"
    code = (
        "import json,sqlite3,duckdb,fastapi;"
        "print(json.dumps({'python':__import__('platform').python_version(),"
        "'sqlite':sqlite3.sqlite_version,'duckdb':duckdb.__version__,"
        "'fastapi':fastapi.__version__}))"
    )
    result = subprocess.run(
        [str(python), "-c", code],
        check=False,
        capture_output=True,
        text=True,
        timeout=15,
    )
    return result.returncode == 0, result.stdout.strip() or result.stderr.strip()


def playwright_browser_present() -> bool:
    cache = Path.home() / ".cache/ms-playwright"
    return cache.exists() and any(cache.glob("chromium-*"))


def required_checks() -> list[Check]:
    checks: list[Check] = []
    required = {
        "git": ("--version",),
        "make": ("--version",),
        "uv": ("--version",),
        "node": ("--version",),
        "pnpm": ("--version",),
    }
    for command, args in required.items():
        version = command_version(command, *args)
        checks.append(
            Check(
                command,
                "ok" if version else "error",
                version or "未安装或无法执行",
                None if version else "安装该工具后重新运行 make bootstrap",
            )
        )

    project_ok, project_detail = project_python_probe()
    checks.append(
        Check(
            "Python 项目环境",
            "ok" if project_ok else "error",
            project_detail,
            None if project_ok else "运行 make bootstrap",
        )
    )
    web_ready = (ROOT / "node_modules/.bin/playwright").exists() and (
        ROOT / "apps/web/node_modules/.bin/vite"
    ).exists()
    checks.append(
        Check(
            "Node 项目依赖",
            "ok" if web_ready else "error",
            "pnpm workspace 已就绪" if web_ready else "node_modules 不完整",
            None if web_ready else "运行 make bootstrap",
        )
    )
    browser_ready = playwright_browser_present()
    checks.append(
        Check(
            "Playwright Chromium",
            "ok" if browser_ready else "error",
            "已安装" if browser_ready else "未找到托管浏览器",
            None if browser_ready else "运行 make bootstrap",
        )
    )
    ports = (
        int(os.getenv("ASTRAMIND_API_PORT", "8010")),
        int(os.getenv("ASTRAMIND_WEB_PORT", "5174")),
    )
    for port in ports:
        available = port_available(port)
        checks.append(
            Check(
                f"端口 {port}",
                "ok" if available else "error",
                "可用" if available else "已被占用",
                None if available else f"停止占用 127.0.0.1:{port} 的进程",
            )
        )

    return checks


def optional_checks() -> list[Check]:
    duckdb_cli = command_version("duckdb", "--version")
    sqlite_cli = command_version("sqlite3", "--version")
    torch_available = importlib.util.find_spec("torch") is not None
    rocm_available = shutil.which("rocminfo") is not None
    return [
        Check("DuckDB CLI（可选）", "ok" if duckdb_cli else "warn", duckdb_cli or "未安装"),
        Check("SQLite CLI（可选）", "ok" if sqlite_cli else "warn", sqlite_cli or "未安装"),
        Check(
            "ROCm/PyTorch（可选）",
            "ok" if torch_available and rocm_available else "warn",
            json.dumps(
                {"torch": torch_available, "rocminfo": rocm_available},
                ensure_ascii=False,
            ),
            "阶段 5 前再完成 GPU 环境配置" if not (torch_available and rocm_available) else None,
        ),
    ]


def collect_checks() -> list[Check]:
    return [*required_checks(), *optional_checks()]


def main() -> int:
    checks = collect_checks()
    labels = {"ok": "通过", "warn": "警告", "error": "失败"}
    for check in checks:
        print(f"[{labels[check.level]}] {check.name}: {check.detail}")
        if check.remedy:
            print(f"  下一步：{check.remedy}")
    errors = sum(check.level == "error" for check in checks)
    print(f"\n诊断完成：{errors} 个必需项失败。")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
