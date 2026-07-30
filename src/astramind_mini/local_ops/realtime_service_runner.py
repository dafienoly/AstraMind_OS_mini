"""Bounded WSL-side runner for the read-only realtime market service."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from astramind_mini.local_ops.realtime_service_runtime import RealtimeStatusStore


def run_realtime_task(make_target: str) -> int:
    if make_target != "realtime-market-service-run":
        raise ValueError("拒绝未知实时服务目标")
    log_root = Path("var/control/realtime-market-service")
    log_root.mkdir(parents=True, exist_ok=True)
    log_path = log_root / "service.log"
    log_path.touch(exist_ok=True)
    try:
        process = subprocess.Popen(
            ["/usr/bin/make", make_target],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
    except OSError as error:
        append_bounded_log(log_path, f"service_start_failed:{type(error).__name__}\n".encode())
        RealtimeStatusStore(log_root).publish(
            "blocked",
            process_state="exited",
            feed_state="blocked",
            projection_state="blocked",
            exit_code=127,
            last_error="service_process_start_failed",
            recovery_action="检查 /usr/bin/make 与任务工作目录后重试",
            successful_heartbeat=False,
        )
        return 127
    assert process.stdout is not None
    while chunk := process.stdout.read(64 * 1024):
        append_bounded_log(log_path, chunk)
    returncode = process.wait()
    _publish_terminal_status(RealtimeStatusStore(log_root), returncode)
    return returncode


def append_bounded_log(
    path: Path,
    payload: bytes,
    *,
    max_bytes: int = 2_000_000,
) -> None:
    if path.is_file() and path.stat().st_size + len(payload) > max_bytes:
        _rotate_logs(path, max_bytes=0)
    with path.open("ab", buffering=0) as stream:
        stream.write(payload[-max_bytes:])
    _truncate_log(path, max_bytes=max_bytes)


def _publish_terminal_status(status_store: RealtimeStatusStore, returncode: int) -> None:
    current = status_store.read()
    terminal_state = (
        current.state
        if returncode == 0 and current is not None
        else "stopped"
        if returncode == 0
        else "blocked"
    )
    status_store.publish(
        terminal_state,
        process_state="exited",
        feed_state=(
            current.feed_state
            if returncode == 0 and current is not None
            else "not_started"
            if returncode == 0
            else "blocked"
        ),
        projection_state=(
            current.projection_state
            if returncode == 0 and current is not None
            else "unknown"
            if returncode == 0
            else "blocked"
        ),
        completed_day_state=current.completed_day_state if current is not None else "unknown",
        exit_code=returncode,
        last_error=(
            current.last_error
            if current is not None and current.last_error
            else "service_process_failed"
            if returncode != 0
            else None
        ),
        retry_failures=current.retry_failures if current is not None else (),
        recovery_action=current.recovery_action if current is not None else None,
        successful_heartbeat=False,
    )


def _rotate_logs(
    path: Path,
    *,
    generations: int = 4,
    max_bytes: int = 2_000_000,
) -> None:
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


__all__ = ["append_bounded_log", "run_realtime_task"]
