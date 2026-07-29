"""WSL adapter for bounded MiniQMT L1 full-push sessions."""

from __future__ import annotations

import asyncio
import shutil
import subprocess
import tempfile
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

from ..application.identity import content_hash
from ..contracts import FeedSessionReport, FeedSessionState, RealtimeQuoteObservation
from .miniqmt_probe import ProbeRunnerError, _parse_body, _terminate_process_tree


class MiniQMTL1Capture:
    def __init__(
        self,
        *,
        runner: Path,
        python_command: str | None,
        xtquant_path: Path | None,
        quote_port: int | None,
        timeout_seconds: float = 30,
    ) -> None:
        self._runner = runner
        self._python_command = python_command
        self._xtquant_path = xtquant_path
        self._quote_port = quote_port
        self._timeout = timeout_seconds

    async def capture(
        self,
        *,
        markets: tuple[str, ...] = ("SH", "SZ", "BJ"),
        seconds: float = 5,
        reconnect_attempts: int = 2,
    ) -> tuple[FeedSessionReport, tuple[RealtimeQuoteObservation, ...], object]:
        started = datetime.now(UTC)
        body, disconnects = await self._invoke_with_reconnect(markets, seconds, reconnect_attempts)
        ended = datetime.now(UTC)
        if not body.get("subscribed") or not body.get("unsubscribed"):
            raise ProbeRunnerError("subscription_lifecycle_incomplete")
        raw_messages = body.get("messages", [])
        if not isinstance(raw_messages, list):
            raise ProbeRunnerError("invalid_runner_response")
        observations, duplicates = normalize_l1_messages(raw_messages, ended)
        session_id = content_hash(
            {
                "provider": "miniqmt",
                "markets": markets,
                "subscribed_at": started,
                "ended_at": ended,
                "raw_hash": content_hash(raw_messages),
            }
        )
        report = FeedSessionReport(
            session_id=session_id,
            provider="miniqmt",
            client_version=str(body.get("client_version", "unknown")),
            state=FeedSessionState.COMPLETE if raw_messages else FeedSessionState.EMPTY,
            markets=markets,
            subscribed_at=started,
            ended_at=ended,
            microbatch_ids=(),
            received_messages=len(raw_messages),
            duplicate_messages=duplicates,
            disconnects=disconnects,
            known_gaps=() if raw_messages else ("bounded_window_no_message",),
        )
        return report, observations, raw_messages

    async def _invoke_with_reconnect(
        self,
        markets: tuple[str, ...],
        seconds: float,
        reconnect_attempts: int,
    ) -> tuple[dict[str, Any], int]:
        if reconnect_attempts < 0 or reconnect_attempts > 5:
            raise ValueError("重连次数必须在 0 到 5 之间")
        for attempt in range(reconnect_attempts + 1):
            body = await self._invoke(markets, seconds)
            error_code = body.get("runner_error_code")
            if not error_code:
                return body, attempt
            if attempt == reconnect_attempts:
                raise ProbeRunnerError(str(error_code))
        raise ProbeRunnerError("reconnect_exhausted")

    async def _invoke(self, markets: tuple[str, ...], seconds: float) -> dict[str, Any]:
        windows_temp = Path("/mnt/c/Windows/Temp")
        with tempfile.TemporaryDirectory(prefix="astramind-l1-", dir=windows_temp) as name:
            command = self._command(Path(name), markets, seconds)
            process = await asyncio.create_subprocess_exec(
                *command,
                cwd=windows_temp,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, _ = await asyncio.wait_for(process.communicate(), timeout=self._timeout)
            except TimeoutError:
                await _terminate_process_tree(process)
                raise ProbeRunnerError("runner_timeout") from None
        return _parse_body(stdout)

    def _command(self, temporary: Path, markets: tuple[str, ...], seconds: float) -> list[str]:
        staged_runner = temporary / "runner.py"
        shutil.copyfile(self._runner, staged_runner)
        python_path = ""
        if self._xtquant_path is not None:
            source = self._xtquant_path / "xtquant"
            if not source.is_dir():
                raise ProbeRunnerError("xtquant_path_invalid")
            target = temporary / "site-packages/xtquant"
            shutil.copytree(source, target)
            python_path = self._windows_path(target.parent)
        arguments = self._interpreter(python_path)
        arguments.extend(
            [
                self._windows_path(staged_runner),
                "--markets",
                ",".join(markets),
                "--seconds",
                str(seconds),
            ]
        )
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


def normalize_l1_messages(
    messages: Sequence[object], received_at: datetime
) -> tuple[tuple[RealtimeQuoteObservation, ...], int]:
    by_identity: dict[str, RealtimeQuoteObservation] = {}
    duplicates = 0
    for message in messages:
        if not isinstance(message, dict):
            continue
        for instrument, payload in cast(dict[object, object], message).items():
            if not isinstance(payload, dict):
                continue
            quote = cast(dict[object, object], payload)
            raw_hash = content_hash(quote)
            observation = RealtimeQuoteObservation(
                instrument_id=str(instrument),
                market_time_ms=_integer(quote.get("time")),
                received_at=received_at,
                last_price=_number(quote.get("lastPrice")),
                previous_close=_number(quote.get("lastClose")),
                open_price=_number(quote.get("open")),
                high_price=_number(quote.get("high")),
                low_price=_number(quote.get("low")),
                volume=_number(quote.get("volume")),
                amount=_number(quote.get("amount")),
                bid_prices=_numbers(quote.get("bidPrice")),
                ask_prices=_numbers(quote.get("askPrice")),
                bid_volumes=_numbers(quote.get("bidVol")),
                ask_volumes=_numbers(quote.get("askVol")),
                stock_status=_optional_integer(quote.get("stockStatus")),
                open_interest=_number(quote.get("openInt")),
                raw_content_hash=raw_hash,
            )
            identity = content_hash(
                {
                    "instrument": observation.instrument_id,
                    "market_time_ms": observation.market_time_ms,
                    "raw": raw_hash,
                }
            )
            if identity in by_identity:
                duplicates += 1
            by_identity[identity] = observation
    return tuple(by_identity[key] for key in sorted(by_identity)), duplicates


def _number(value: object) -> float | None:
    return float(value) if isinstance(value, int | float) and value >= 0 else None


def _integer(value: object) -> int | None:
    return int(value) if isinstance(value, int | float) and value >= 0 else None


def _optional_integer(value: object) -> int | None:
    return int(value) if isinstance(value, int | float) else None


def _numbers(value: object) -> tuple[float, ...]:
    if not isinstance(value, list | tuple):
        return ()
    return tuple(float(item) for item in value if isinstance(item, int | float) and item >= 0)


def quote_is_stale(
    observation: RealtimeQuoteObservation,
    *,
    now: datetime,
    maximum_age: timedelta = timedelta(seconds=10),
) -> bool:
    if now.tzinfo is None:
        raise ValueError("新鲜度判断时间必须带时区")
    return now - observation.received_at > maximum_age


__all__ = ["MiniQMTL1Capture", "normalize_l1_messages", "quote_is_stale"]
