"""Run local API and diagnostic web processes with reliable cleanup."""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
from pathlib import Path

from astramind_mini.config import get_settings

ROOT = Path(__file__).resolve().parents[1]

# Uvicorn defaults to watching the whole working tree for ``--reload``.  This
# repository also contains large, frequently changing runtime data under
# ``var/``; watching it on WSL makes the watchfiles thread busy-loop and can
# starve the local API.  Keep the API reload loop scoped to Python sources.
API_RELOAD_DIRS = (
    ROOT / "src",
    ROOT / "apps/api",
    ROOT / "scripts",
)
API_RELOAD_ARGS = tuple(
    argument for path in API_RELOAD_DIRS for argument in ("--reload-dir", str(path))
)
API_GRACEFUL_SHUTDOWN_SECONDS = 3


def ensure_ready() -> None:
    missing: list[str] = []
    if not (ROOT / ".venv/bin/uvicorn").exists():
        missing.append("Python 项目依赖")
    if not (ROOT / "apps/web/node_modules/.bin/vite").exists():
        missing.append("Node 项目依赖")
    if shutil.which("pnpm") is None:
        missing.append("pnpm")
    if missing:
        raise RuntimeError(f"{'、'.join(missing)}未就绪；请先运行 make bootstrap")


def stop(processes: list[subprocess.Popen[bytes]]) -> None:
    for process in processes:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            continue
    for process in processes:
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)


def main() -> int:
    ensure_ready()
    settings = get_settings()
    processes = [
        subprocess.Popen(
            [
                str(ROOT / ".venv/bin/uvicorn"),
                "apps.api.main:app",
                "--reload",
                *API_RELOAD_ARGS,
                "--host",
                settings.api_host,
                "--port",
                str(settings.api_port),
                "--timeout-graceful-shutdown",
                str(API_GRACEFUL_SHUTDOWN_SECONDS),
            ],
            cwd=ROOT,
            start_new_session=True,
        ),
        subprocess.Popen(
            [
                str(ROOT / "apps/web/node_modules/.bin/vite"),
                "--host",
                "127.0.0.1",
                "--port",
                str(settings.web_port),
            ],
            cwd=ROOT / "apps/web",
            start_new_session=True,
        ),
    ]
    print(
        f"API: http://{settings.api_host}:{settings.api_port} | "
        f"诊断页: http://127.0.0.1:{settings.web_port}"
    )
    try:
        while all(process.poll() is None for process in processes):
            processes[0].wait(timeout=1)
    except subprocess.TimeoutExpired:
        return main_loop(processes)
    except KeyboardInterrupt:
        return 0
    finally:
        stop(processes)
    return next((process.returncode or 1 for process in processes if process.returncode), 0)


def main_loop(processes: list[subprocess.Popen[bytes]]) -> int:
    try:
        while all(process.poll() is None for process in processes):
            for process in processes:
                try:
                    process.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    continue
    except KeyboardInterrupt:
        return 0
    return next((process.returncode or 1 for process in processes if process.returncode), 0)


if __name__ == "__main__":
    sys.exit(main())
