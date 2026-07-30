"""Persistent WSL client for the read-only Windows XtQuant data bridge."""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import re
import subprocess
import uuid
from collections import deque
from collections.abc import AsyncIterator
from pathlib import Path


class MiniQMTBridgeError(RuntimeError):
    def __init__(self, code: str, detail: str | None = None) -> None:
        super().__init__(code)
        self.code = code
        self.detail = detail


class MiniQMTBridgeClient:
    def __init__(
        self,
        *,
        runner: Path,
        xtquant_path: Path,
        quote_port: int,
        python_command: str = "py",
        startup_timeout_seconds: float = 10,
        event_queue_size: int = 256,
    ) -> None:
        self._runner = runner
        self._xtquant_path = xtquant_path
        self._quote_port = quote_port
        self._python = python_command
        self._startup_timeout = startup_timeout_seconds
        self._event_queue_size = event_queue_size
        self._events: asyncio.Queue[dict[str, object]] = asyncio.Queue(event_queue_size)
        self._pending: dict[str, asyncio.Future[dict[str, object]]] = {}
        self._process: asyncio.subprocess.Process | None = None
        self._reader_task: asyncio.Task[None] | None = None
        self._stderr_task: asyncio.Task[None] | None = None
        self._provider_version = "unknown"
        self._client_fingerprint = "unknown"
        self._overflowed = False
        self._write_lock = asyncio.Lock()
        self._interop_socket: str | None = None
        self._windows_process_id: int | None = None
        self._stderr_lines: deque[str] = deque(maxlen=20)

    @property
    def stderr_tail(self) -> tuple[str, ...]:
        return tuple(self._stderr_lines)

    @property
    def provider_version(self) -> str:
        return self._provider_version

    @property
    def client_fingerprint(self) -> str:
        return self._client_fingerprint

    async def start(self) -> None:
        if self._process is not None and self._process.returncode is None:
            return
        if not self._runner.is_file() or not (self._xtquant_path / "xtquant").is_dir():
            raise MiniQMTBridgeError("bridge_configuration_invalid")
        for attempt in range(3):
            self._events = asyncio.Queue(self._event_queue_size)
            self._overflowed = False
            await self._spawn()
            try:
                async with asyncio.timeout(self._startup_timeout):
                    ready = await self._events.get()
                    while ready.get("type") != "ready":
                        ready = await self._events.get()
            except TimeoutError:
                await self._force_stop()
                if attempt == 2:
                    raise MiniQMTBridgeError(
                        "bridge_startup_timeout",
                        "\n".join(self._stderr_lines) or None,
                    ) from None
                await asyncio.sleep(0.5 * (attempt + 1))
                continue
            self._provider_version = str(ready.get("provider_version", "unknown"))
            self._client_fingerprint = str(ready.get("client_fingerprint", "unknown"))
            process_id = ready.get("process_id")
            self._windows_process_id = process_id if isinstance(process_id, int) else None
            return

    async def _spawn(self) -> None:
        environment = await self._working_interop_environment()
        self._process = await asyncio.create_subprocess_exec(
            *self._command(),
            cwd=Path("/mnt/c/Windows/Temp"),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            limit=64 * 1024 * 1024,
            env=environment,
        )
        self._reader_task = asyncio.create_task(self._read_stdout())
        self._stderr_task = asyncio.create_task(self._drain_stderr())

    async def _working_interop_environment(self) -> dict[str, str]:
        environment = dict(os.environ)
        interop_root = Path("/run/WSL")
        if not interop_root.is_dir():
            return environment
        current = environment.get("WSL_INTEROP")
        discovered = sorted(
            interop_root.glob("*_interop"),
            key=lambda path: path.stat().st_mtime_ns,
            reverse=True,
        )
        candidates = tuple(
            dict.fromkeys(
                [
                    *(path for path in (current,) if path),
                    *(str(path) for path in discovered[:8]),
                ]
            )
        )
        for candidate in candidates:
            probe_environment = {**environment, "WSL_INTEROP": candidate}
            if await self._interop_works(probe_environment):
                self._interop_socket = candidate
                return probe_environment
        raise MiniQMTBridgeError("windows_interop_unavailable")

    @staticmethod
    async def _interop_works(environment: dict[str, str]) -> bool:
        process = await asyncio.create_subprocess_exec(
            "/mnt/c/Windows/System32/cmd.exe",
            "/d",
            "/c",
            "exit 0",
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=environment,
        )
        try:
            async with asyncio.timeout(1):
                return await process.wait() == 0
        except TimeoutError:
            with contextlib.suppress(ProcessLookupError):
                process.kill()
            with contextlib.suppress(TimeoutError):
                async with asyncio.timeout(1):
                    await process.wait()
            return False

    async def stop(self) -> None:
        process = self._process
        if process is None:
            return
        if process.returncode is None:
            try:
                await self.request("shutdown", timeout_seconds=3)
            except (MiniQMTBridgeError, TimeoutError):
                with contextlib.suppress(ProcessLookupError):
                    process.terminate()
            try:
                async with asyncio.timeout(3):
                    await process.wait()
            except TimeoutError:
                process.kill()
                await process.wait()
        if self._reader_task is not None:
            self._reader_task.cancel()
        if self._stderr_task is not None:
            self._stderr_task.cancel()
        self._process = None
        self._windows_process_id = None

    async def _force_stop(self) -> None:
        await self._terminate_windows_process()
        process = self._process
        if process is not None and process.returncode is None:
            with contextlib.suppress(ProcessLookupError):
                process.terminate()
            try:
                async with asyncio.timeout(2):
                    await process.wait()
            except TimeoutError:
                with contextlib.suppress(ProcessLookupError):
                    process.kill()
        if self._reader_task is not None:
            self._reader_task.cancel()
        if self._stderr_task is not None:
            self._stderr_task.cancel()
        self._process = None
        self._windows_process_id = None

    async def _terminate_windows_process(self) -> None:
        process_id = self._windows_process_id
        if process_id is None:
            return
        environment = dict(os.environ)
        if self._interop_socket is not None:
            environment["WSL_INTEROP"] = self._interop_socket
        process = await asyncio.create_subprocess_exec(
            "/mnt/c/Windows/System32/taskkill.exe",
            "/pid",
            str(process_id),
            "/t",
            "/f",
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=environment,
        )
        with contextlib.suppress(TimeoutError):
            async with asyncio.timeout(3):
                await process.wait()

    async def request(
        self,
        command: str,
        *,
        timeout_seconds: float = 30,
        **payload: object,
    ) -> dict[str, object]:
        await self.start()
        process = self._process
        if process is None or process.stdin is None or process.returncode is not None:
            raise MiniQMTBridgeError("bridge_disconnected")
        request_id = uuid.uuid4().hex
        future = asyncio.get_running_loop().create_future()
        self._pending[request_id] = future
        body = {"request_id": request_id, "command": command, **payload}
        async with self._write_lock:
            process.stdin.write(
                (json.dumps(body, ensure_ascii=True, separators=(",", ":")) + "\n").encode()
            )
            await process.stdin.drain()
        try:
            async with asyncio.timeout(timeout_seconds):
                response = await future
        except TimeoutError:
            self._pending.pop(request_id, None)
            await self._force_stop()
            raise MiniQMTBridgeError("bridge_request_timeout") from None
        if not response.get("ok"):
            raise MiniQMTBridgeError(str(response.get("error_code", "bridge_request_failed")))
        result = response.get("result", {})
        if not isinstance(result, dict):
            raise MiniQMTBridgeError("bridge_invalid_response")
        return result

    async def quote_events(self) -> AsyncIterator[dict[str, object]]:
        while True:
            if self._overflowed:
                raise MiniQMTBridgeError("quote_event_queue_overflow")
            value = await self._events.get()
            if value.get("type") == "event" and value.get("event") == "quote":
                yield value

    async def next_quote_event(self, *, timeout_seconds: float = 1) -> dict[str, object] | None:
        if self._overflowed:
            raise MiniQMTBridgeError("quote_event_queue_overflow")
        try:
            async with asyncio.timeout(timeout_seconds):
                while True:
                    value = await self._events.get()
                    if value.get("type") == "event" and value.get("event") == "quote":
                        return value
        except TimeoutError:
            return None

    async def _read_stdout(self) -> None:
        process = self._process
        assert process is not None and process.stdout is not None
        while line := await process.stdout.readline():
            try:
                value = json.loads(line)
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue
            if not isinstance(value, dict):
                continue
            request_id = value.get("request_id")
            if value.get("type") == "response" and isinstance(request_id, str):
                future = self._pending.pop(request_id, None)
                if future is not None and not future.done():
                    future.set_result(value)
                continue
            try:
                self._events.put_nowait(value)
            except asyncio.QueueFull:
                self._overflowed = True
        error = MiniQMTBridgeError(
            "bridge_disconnected",
            "\n".join(self._stderr_lines) or None,
        )
        for future in self._pending.values():
            if not future.done():
                future.set_exception(error)
        self._pending.clear()

    async def _drain_stderr(self) -> None:
        process = self._process
        assert process is not None and process.stderr is not None
        while line := await process.stderr.readline():
            text = line.decode(errors="replace").strip()
            if text:
                self._stderr_lines.append(_redact_stderr(text[-1000:]))

    def _command(self) -> list[str]:
        interpreter = self._python
        launcher_arguments: list[str] = []
        if interpreter.endswith(".exe") and interpreter.startswith("/"):
            interpreter = self._windows_path(Path(interpreter))
        if interpreter.lower().rsplit("\\", 1)[-1] in {"py", "py.exe"}:
            launcher_arguments.append("-3.11")
        arguments = [
            interpreter,
            *launcher_arguments,
            self._windows_path(self._runner),
            "--xtquant-path",
            self._windows_path(self._xtquant_path),
            "--quote-port",
            str(self._quote_port),
        ]
        return [
            "/mnt/c/Windows/System32/cmd.exe",
            "/d",
            "/c",
            subprocess.list2cmdline(arguments),
        ]

    @staticmethod
    def _windows_path(path: Path) -> str:
        result = subprocess.run(
            ["wslpath", "-w", str(path.resolve())],
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()


def _redact_stderr(value: str) -> str:
    value = re.sub(r"(?i)c:\\users\\[^\\\s]+", r"C:\\Users\\<redacted>", value)
    return re.sub(r"/home/[^/\s]+", "/home/<redacted>", value)


def sanitize_bridge_failure(code: str, detail: str | None) -> tuple[str, str | None]:
    safe_code = code if re.fullmatch(r"[a-z][a-z0-9_]{2,63}", code) else "bridge_external_error"
    safe_detail = _redact_sensitive_values(_redact_stderr(detail[-4000:])) if detail else None
    return safe_code, safe_detail


def _redact_sensitive_values(value: str) -> str:
    key = r"(?:token|api[_ -]?key|secret|password|account(?:_id)?)"
    pattern = re.compile(
        rf"""(?ix)
        (?<![\\/])(?P<prefix>["']?{key}["']?\s*(?::|=|\s)\s*)
        ["']?[^"'\s,;]+["']?
        """
    )
    return pattern.sub(lambda match: f"{match.group('prefix')}<redacted>", value)


__all__ = ["MiniQMTBridgeClient", "MiniQMTBridgeError", "sanitize_bridge_failure"]
