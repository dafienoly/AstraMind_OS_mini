"""WSL adapter for one persistent, read-only MiniQMT Paper handshake."""

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

from ..contracts.paper_startup import (
    PaperStartupEvidence,
)
from ..domain.paper_startup import (
    build_callback_handshake,
    build_mode_lock,
    build_paper_account_baseline,
)
from .miniqmt_account import MiniQMTAccountError, _parse_body, _terminate_process_tree
from .miniqmt_account_normalization import build_account_snapshot
from .windows_runner_diagnostics import classify_runner_failure, record_runner_diagnostic


class MiniQMTPaperReadonlyClient:
    def __init__(
        self,
        *,
        runner: Path,
        python_command: str | None,
        xtquant_path: Path | None,
        userdata_path: str,
        account_selector: str,
        account_mode: str,
        fingerprint_key: str,
        callback_wait_seconds: float = 2,
        timeout_seconds: float = 20,
        diagnostic_root: Path | None = None,
    ) -> None:
        self._runner = runner
        self._python_command = python_command
        self._xtquant_path = xtquant_path
        self._userdata_path = userdata_path
        self._account_selector = account_selector
        self._account_mode = account_mode
        self._fingerprint_key = fingerprint_key
        self._callback_wait = callback_wait_seconds
        self._timeout = timeout_seconds
        self._diagnostic_root = diagnostic_root

    async def read(self) -> PaperStartupEvidence:
        if self._account_mode != "simulation":
            raise MiniQMTAccountError("simulation_mode_required")
        body = await self._invoke()
        verified_at = datetime.now(UTC)
        lock = build_mode_lock(
            configured_mode=str(body.get("account_mode")),
            broker_account_matched=body.get("account_matched") is True,
            broker_account_type=_integer(body, "account_type"),
            broker_account_classification=_optional_integer(body, "account_classification"),
            broker_account_status=_integer(body, "account_status"),
            client_version=_text(body, "client_version"),
            gateway_version=_text(body, "gateway_version"),
            verified_at=verified_at,
        )
        snapshot = build_account_snapshot(
            account_mode="simulation",
            account_fingerprint=_text(body, "account_fingerprint"),
            as_of=verified_at,
            asset=_mapping(body, "asset"),
            positions=_sequence(body, "positions"),
            orders=_sequence(body, "orders"),
            trades=_sequence(body, "trades"),
            client_version=lock.client_version,
            gateway_version=lock.gateway_version,
            known_gaps=("non_atomic_queries_within_one_readonly_session",),
        )
        handshake = build_callback_handshake(
            mode_lock=lock,
            snapshot=snapshot,
            subscribed=body.get("subscribed") is True,
            unsubscribed=body.get("unsubscribed") is True,
            callback_types=tuple(str(item) for item in _sequence(body, "callback_types")),
            callback_count=_integer(body, "callback_count"),
            foreign_account_callback_count=_integer(body, "foreign_account_callback_count"),
            disconnected=body.get("disconnected") is True,
            started_at=_epoch(body, "started_at_epoch"),
            completed_at=_epoch(body, "completed_at_epoch"),
        )
        baseline = build_paper_account_baseline(
            snapshot,
            lock,
            handshake,
            created_at=verified_at,
        )
        return PaperStartupEvidence(
            mode_lock=lock,
            account_snapshot=snapshot,
            callback_handshake=handshake,
            account_baseline=baseline,
        )

    async def _invoke(self) -> dict[str, Any]:
        windows_temp = Path("/mnt/c/Windows/Temp")
        with tempfile.TemporaryDirectory(prefix="astramind-paper-", dir=windows_temp) as name:
            temporary = Path(name)
            command = self._staged_command(temporary)
            process = await asyncio.create_subprocess_exec(
                *command,
                cwd=windows_temp,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=self._timeout,
                )
            except TimeoutError:
                await _terminate_process_tree(process)
                self._record(b"", b"", process.returncode, "paper_readonly_handshake_timeout")
                raise MiniQMTAccountError("paper_readonly_handshake_timeout") from None
            try:
                body = _parse_body(stdout)
            except MiniQMTAccountError:
                code = classify_runner_failure(
                    stdout=stdout,
                    stderr=stderr,
                    body=None,
                    default="invalid_runner_json",
                )
                self._record(stdout, stderr, process.returncode, code)
                raise MiniQMTAccountError(code) from None
            if process.returncode != 0 or body.get("runner_error_code"):
                code = classify_runner_failure(
                    stdout=stdout,
                    stderr=stderr,
                    body=body,
                    default="paper_readonly_handshake_failed",
                )
                self._record(stdout, stderr, process.returncode, code)
                raise MiniQMTAccountError(code)
            self._record(stdout, stderr, process.returncode, "ok")
            return body

    def _record(
        self,
        stdout: bytes,
        stderr: bytes,
        returncode: int | None,
        outcome: str,
    ) -> None:
        record_runner_diagnostic(
            root=self._diagnostic_root,
            runner="paper-readonly",
            stdout=stdout,
            stderr=stderr,
            returncode=returncode,
            outcome=outcome,
            secrets=(self._account_selector, self._userdata_path, self._fingerprint_key),
        )

    def _staged_command(self, temporary: Path) -> list[str]:
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
            "ASTRAMIND_MINIQMT_CALLBACK_WAIT_SECONDS": self._callback_wait,
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


def _text(body: dict[str, Any], key: str) -> str:
    value = body.get(key)
    if not isinstance(value, str) or not value:
        raise MiniQMTAccountError("invalid_paper_readonly_payload")
    return value


def _integer(body: dict[str, Any], key: str) -> int:
    value = body.get(key)
    if not isinstance(value, int):
        raise MiniQMTAccountError("invalid_paper_readonly_payload")
    return value


def _optional_integer(body: dict[str, Any], key: str) -> int | None:
    value = body.get(key)
    if value is None:
        return None
    if not isinstance(value, int):
        raise MiniQMTAccountError("invalid_paper_readonly_payload")
    return value


def _mapping(body: dict[str, Any], key: str) -> dict[str, object]:
    value = body.get(key)
    if not isinstance(value, dict):
        raise MiniQMTAccountError("invalid_paper_readonly_payload")
    return {str(name): item for name, item in value.items()}


def _sequence(body: dict[str, Any], key: str) -> list[object]:
    value = body.get(key)
    if not isinstance(value, list):
        raise MiniQMTAccountError("invalid_paper_readonly_payload")
    return value


def _epoch(body: dict[str, Any], key: str) -> datetime:
    value = body.get(key)
    if not isinstance(value, int | float):
        raise MiniQMTAccountError("invalid_paper_readonly_payload")
    return datetime.fromtimestamp(float(value), tz=UTC)


__all__ = ["MiniQMTPaperReadonlyClient"]
