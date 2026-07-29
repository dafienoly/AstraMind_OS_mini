"""WSL bridge for one bounded MiniQMT canary quote."""

from __future__ import annotations

import asyncio
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .miniqmt_account import MiniQMTAccountError, _parse_body, _terminate_process_tree
from .windows_runner_diagnostics import classify_runner_failure, record_runner_diagnostic


@dataclass(frozen=True, slots=True)
class CanaryQuote:
    instrument_id: str
    best_ask: float
    last_close: float
    limit_up: float
    risk_warning: bool
    listed_long_enough: bool
    instrument_detail_available: bool
    market_time: datetime
    received_at: datetime

    @property
    def tradable(self) -> bool:
        return (
            self.instrument_detail_available
            and self.listed_long_enough
            and not self.risk_warning
            and self.best_ask <= self.limit_up
        )


class MiniQMTCanaryQuoteReader:
    def __init__(
        self,
        *,
        runner: Path,
        python_command: str | None,
        xtquant_path: Path | None,
        quote_port: int | None,
        timeout_seconds: float = 10,
        fresh_wait_seconds: float = 8,
        diagnostic_root: Path | None = None,
    ) -> None:
        self._runner = runner
        self._python_command = python_command
        self._xtquant_path = xtquant_path
        self._quote_port = quote_port
        self._timeout = timeout_seconds
        self._fresh_wait = fresh_wait_seconds
        self._diagnostic_root = diagnostic_root

    async def read(self, instrument_id: str) -> CanaryQuote:
        body = await self._invoke(instrument_id)
        received_at = datetime.now(UTC)
        best_ask = body.get("best_ask")
        last_close = body.get("last_close")
        limit_up = body.get("limit_up")
        market_time_ms = body.get("market_time_ms")
        if not isinstance(best_ask, int | float) or best_ask <= 0:
            raise MiniQMTAccountError("best_ask_unavailable")
        if not isinstance(market_time_ms, int | float) or market_time_ms <= 0:
            raise MiniQMTAccountError("market_time_unavailable")
        if not isinstance(last_close, int | float) or last_close <= 0:
            raise MiniQMTAccountError("last_close_unavailable")
        if not isinstance(limit_up, int | float) or limit_up <= 0:
            raise MiniQMTAccountError("price_limit_unavailable")
        flags = ("risk_warning", "listed_long_enough", "instrument_detail_available")
        if any(not isinstance(body.get(name), bool) for name in flags):
            raise MiniQMTAccountError("instrument_detail_invalid")
        return CanaryQuote(
            instrument_id=instrument_id,
            best_ask=float(best_ask),
            last_close=float(last_close),
            limit_up=float(limit_up),
            risk_warning=bool(body["risk_warning"]),
            listed_long_enough=bool(body["listed_long_enough"]),
            instrument_detail_available=bool(body["instrument_detail_available"]),
            market_time=datetime.fromtimestamp(float(market_time_ms) / 1000, tz=UTC),
            received_at=received_at,
        )

    async def _invoke(self, instrument_id: str) -> dict[str, Any]:
        windows_temp = Path("/mnt/c/Windows/Temp")
        with tempfile.TemporaryDirectory(
            prefix="astramind-canary-quote-", dir=windows_temp
        ) as name:
            temporary = Path(name)
            command = self._command(temporary, instrument_id)
            process = await asyncio.create_subprocess_exec(
                *command,
                cwd=windows_temp,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(), timeout=self._timeout
                )
            except TimeoutError:
                await _terminate_process_tree(process)
                record_runner_diagnostic(
                    root=self._diagnostic_root,
                    runner="canary-quote",
                    stdout=b"",
                    stderr=b"",
                    returncode=process.returncode,
                    outcome="canary_quote_timeout",
                )
                raise MiniQMTAccountError("canary_quote_timeout") from None
            try:
                body = _parse_body(stdout)
            except MiniQMTAccountError:
                code = classify_runner_failure(
                    stdout=stdout,
                    stderr=stderr,
                    body=None,
                    default="invalid_runner_json",
                )
                record_runner_diagnostic(
                    root=self._diagnostic_root,
                    runner="canary-quote",
                    stdout=stdout,
                    stderr=stderr,
                    returncode=process.returncode,
                    outcome=code,
                )
                raise MiniQMTAccountError(code) from None
            if process.returncode != 0 or body.get("runner_error_code"):
                code = classify_runner_failure(
                    stdout=stdout,
                    stderr=stderr,
                    body=body,
                    default="canary_quote_failed",
                )
                record_runner_diagnostic(
                    root=self._diagnostic_root,
                    runner="canary-quote",
                    stdout=stdout,
                    stderr=stderr,
                    returncode=process.returncode,
                    outcome=code,
                )
                raise MiniQMTAccountError(code)
            record_runner_diagnostic(
                root=self._diagnostic_root,
                runner="canary-quote",
                stdout=stdout,
                stderr=stderr,
                returncode=process.returncode,
                outcome="ok",
            )
            return body

    def _command(self, temporary: Path, instrument_id: str) -> list[str]:
        runner = temporary / "runner.py"
        shutil.copyfile(self._runner, runner)
        python_path = self._stage_xtquant(temporary)
        arguments = [
            *self._interpreter(python_path),
            self._windows_path(runner),
            "--instrument",
            instrument_id,
            "--fresh-wait-seconds",
            str(self._fresh_wait),
        ]
        if python_path:
            arguments.extend(["--xtquant-path", python_path])
        if self._quote_port is not None:
            arguments.extend(["--quote-port", str(self._quote_port)])
        return [
            "/mnt/c/Windows/System32/cmd.exe",
            "/d",
            "/c",
            subprocess.list2cmdline(arguments),
        ]

    def _stage_xtquant(self, temporary: Path) -> str:
        if self._xtquant_path is None:
            return ""
        source = self._xtquant_path / "xtquant"
        if not source.is_dir():
            raise MiniQMTAccountError("xtquant_path_invalid")
        target = temporary / "site-packages/xtquant"
        shutil.copytree(source, target)
        return self._windows_path(target.parent)

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


__all__ = ["CanaryQuote", "MiniQMTCanaryQuoteReader"]
