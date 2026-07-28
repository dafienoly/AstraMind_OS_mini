"""WSL adapter for four isolated, read-only MiniQMT account queries."""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ..contracts.account import AccountMode, AccountSnapshot
from .miniqmt_account_normalization import build_account_snapshot

INTERFACES = ("asset", "positions", "orders", "trades")


class MiniQMTAccountError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class MiniQMTAccountClient:
    def __init__(
        self,
        *,
        runner: Path,
        python_command: str | None,
        xtquant_path: Path | None,
        userdata_path: str,
        account_selector: str,
        account_mode: AccountMode,
        fingerprint_key: str,
        timeout_seconds: float = 15,
    ) -> None:
        self._runner = runner
        self._python_command = python_command
        self._xtquant_path = xtquant_path
        self._userdata_path = userdata_path
        self._account_selector = account_selector
        self._account_mode = account_mode
        self._fingerprint_key = fingerprint_key
        self._timeout = timeout_seconds

    async def read(self) -> AccountSnapshot:
        bodies = {interface: await self._invoke(interface) for interface in INTERFACES}
        fingerprints = {str(body.get("account_fingerprint")) for body in bodies.values()}
        modes = {str(body.get("account_mode")) for body in bodies.values()}
        client_versions = {str(body.get("client_version")) for body in bodies.values()}
        gateway_versions = {str(body.get("gateway_version")) for body in bodies.values()}
        if (
            len(fingerprints) != 1
            or len(modes) != 1
            or modes != {self._account_mode}
            or len(client_versions) != 1
            or len(gateway_versions) != 1
        ):
            raise MiniQMTAccountError("query_identity_conflict")
        as_of = datetime.now(UTC)
        return build_account_snapshot(
            account_mode=self._account_mode,
            account_fingerprint=fingerprints.pop(),
            as_of=as_of,
            asset=_dict_data(bodies["asset"]),
            positions=_list_data(bodies["positions"]),
            orders=_list_data(bodies["orders"]),
            trades=_list_data(bodies["trades"]),
            client_version=client_versions.pop(),
            gateway_version=gateway_versions.pop(),
        )

    async def _invoke(self, interface: str) -> dict[str, Any]:
        windows_temp = Path("/mnt/c/Windows/Temp")
        with tempfile.TemporaryDirectory(prefix="astramind-account-", dir=windows_temp) as name:
            temporary = Path(name)
            command = self._staged_command(temporary, interface)
            process = await asyncio.create_subprocess_exec(
                *command,
                cwd=windows_temp,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, _ = await asyncio.wait_for(
                    process.communicate(),
                    timeout=self._timeout,
                )
            except TimeoutError:
                await _terminate_process_tree(process)
                raise MiniQMTAccountError(f"{interface}_timeout") from None
            body = _parse_body(stdout)
            if process.returncode != 0 or body.get("runner_error_code"):
                raise MiniQMTAccountError(f"{interface}_query_failed")
            if body.get("interface") != interface:
                raise MiniQMTAccountError("query_interface_conflict")
            return body

    def _staged_command(self, temporary: Path, interface: str) -> list[str]:
        staged_runner = temporary / "runner.py"
        shutil.copyfile(self._runner, staged_runner)
        python_path = ""
        if self._xtquant_path is not None:
            source = self._xtquant_path / "xtquant"
            if not source.is_dir():
                raise MiniQMTAccountError("xtquant_path_invalid")
            target = temporary / "site-packages/xtquant"
            shutil.copytree(source, target)
            python_path = self._windows_path(target.parent)
        config = {
            "ASTRAMIND_MINIQMT_ACCOUNT_ID": self._account_selector,
            "ASTRAMIND_MINIQMT_ACCOUNT_MODE": self._account_mode,
            "ASTRAMIND_MINIQMT_USERDATA_PATH": self._userdata_path,
            "ASTRAMIND_MINIQMT_FINGERPRINT_KEY": self._fingerprint_key,
            "ASTRAMIND_MINIQMT_XTQUANT_PATH": python_path or None,
        }
        config_path = temporary / "config.json"
        descriptor = config_path.open("x", encoding="utf-8")
        try:
            os.chmod(config_path, 0o600)
            json.dump(config, descriptor)
        finally:
            descriptor.close()
        arguments = [
            *self._interpreter(python_path),
            self._windows_path(staged_runner),
            "--interface",
            interface,
            "--config",
            self._windows_path(config_path),
        ]
        return [
            "/mnt/c/Windows/System32/cmd.exe",
            "/d",
            "/c",
            subprocess.list2cmdline(arguments),
        ]

    def _interpreter(self, python_path: str) -> list[str]:
        if self._python_command:
            return [self._python_command]
        return ["py", "-3.11" if python_path else "-3.12"]

    @staticmethod
    def _windows_path(path: Path) -> str:
        result = subprocess.run(
            ["wslpath", "-w", str(path.resolve())],
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()


def _dict_data(body: dict[str, Any]) -> dict[str, object]:
    value = body.get("data")
    if not isinstance(value, dict):
        raise MiniQMTAccountError("invalid_query_payload")
    return {str(key): item for key, item in value.items()}


def _list_data(body: dict[str, Any]) -> list[object]:
    value = body.get("data")
    if not isinstance(value, list):
        raise MiniQMTAccountError("invalid_query_payload")
    return value


def _parse_body(payload: bytes) -> dict[str, Any]:
    text = payload.decode("utf-8-sig", errors="replace")
    for line in reversed(text.splitlines()):
        if not line.lstrip().startswith("{"):
            continue
        try:
            value: object = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    raise MiniQMTAccountError("invalid_runner_json")


async def _terminate_process_tree(process: asyncio.subprocess.Process) -> None:
    taskkill = Path("/mnt/c/Windows/System32/taskkill.exe")
    if taskkill.is_file() and process.pid is not None:
        cleanup = await asyncio.create_subprocess_exec(
            str(taskkill),
            "/PID",
            str(process.pid),
            "/T",
            "/F",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await cleanup.wait()
    if process.returncode is None:
        process.kill()
        await process.wait()


__all__ = [
    "MiniQMTAccountClient",
    "MiniQMTAccountError",
    "build_account_snapshot",
]
