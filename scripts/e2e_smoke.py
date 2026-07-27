"""Run the visible browser smoke workflow against temporary local processes."""

from __future__ import annotations

import os
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def wait_for(url: str, timeout: float = 25.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                if response.status < 500:
                    return
        except (urllib.error.URLError, TimeoutError):
            time.sleep(0.25)
    raise RuntimeError(f"服务未在 {timeout:.0f} 秒内就绪：{url}")


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


def wait_until_closed(port: int, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                time.sleep(0.1)
        except OSError:
            return
    raise RuntimeError(f"烟测退出后端口仍未释放: 127.0.0.1:{port}")


def main() -> int:
    processes = [
        subprocess.Popen(
            [
                str(ROOT / ".venv/bin/uvicorn"),
                "apps.api.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                "8010",
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
                "5174",
            ],
            cwd=ROOT / "apps/web",
            start_new_session=True,
        ),
    ]
    try:
        wait_for("http://127.0.0.1:8010/healthz")
        wait_for("http://127.0.0.1:5174")
        result = subprocess.run(
            ["pnpm", "exec", "playwright", "test"],
            cwd=ROOT,
            check=False,
        )
        return result.returncode
    finally:
        stop(processes)
        wait_until_closed(8010)
        wait_until_closed(5174)


if __name__ == "__main__":
    sys.exit(main())
