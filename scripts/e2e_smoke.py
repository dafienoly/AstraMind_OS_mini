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

from e2e_rotation_fixture import (  # type: ignore[import-not-found]
    prepare,
    prepare_daily_statuses,
    prepare_data_snapshot,
)

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


def free_port() -> int:
    with socket.socket() as candidate:
        candidate.bind(("127.0.0.1", 0))
        return int(candidate.getsockname()[1])


def main() -> int:
    rotation_fixture = ROOT / "var/e2e/rotation"
    data_fixture = ROOT / "var/e2e/data"
    control_fixture = ROOT / "var/e2e/control"
    prepare(rotation_fixture)
    prepare_data_snapshot(data_fixture)
    prepare_daily_statuses(
        data_root=data_fixture,
        control_db=control_fixture / "astramind.db",
        local_ops_db=control_fixture / "local-ops.sqlite3",
        decision_root=ROOT / "var/e2e/daily-decision",
    )
    api_port = free_port()
    web_port = free_port()
    api_environment = {
        **os.environ,
        "ASTRAMIND_ENVIRONMENT": "test",
        "ASTRAMIND_API_PORT": str(api_port),
        "ASTRAMIND_WEB_PORT": str(web_port),
        "ASTRAMIND_ROTATION_DATA_DIR": str(rotation_fixture),
        "ASTRAMIND_DATA_DIR": str(data_fixture),
        "ASTRAMIND_CONTROL_DB_PATH": str(control_fixture / "astramind.db"),
        "ASTRAMIND_LOCAL_OPS_DB_PATH": str(control_fixture / "local-ops.sqlite3"),
    }
    web_environment = {
        **os.environ,
        "VITE_API_BASE_URL": f"http://127.0.0.1:{api_port}",
    }
    processes = [
        subprocess.Popen(
            [
                str(ROOT / ".venv/bin/uvicorn"),
                "apps.api.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(api_port),
            ],
            cwd=ROOT,
            env=api_environment,
            start_new_session=True,
        ),
        subprocess.Popen(
            [
                str(ROOT / "apps/web/node_modules/.bin/vite"),
                "--host",
                "127.0.0.1",
                "--port",
                str(web_port),
            ],
            cwd=ROOT / "apps/web",
            env=web_environment,
            start_new_session=True,
        ),
    ]
    try:
        wait_for(f"http://127.0.0.1:{api_port}/healthz")
        wait_for(f"http://127.0.0.1:{web_port}")
        result = subprocess.run(
            ["pnpm", "exec", "playwright", "test"],
            cwd=ROOT,
            env={
                **os.environ,
                "ASTRAMIND_E2E_BASE_URL": f"http://127.0.0.1:{web_port}",
            },
            check=False,
        )
        return result.returncode
    finally:
        stop(processes)
        wait_until_closed(api_port)
        wait_until_closed(web_port)


if __name__ == "__main__":
    sys.exit(main())
