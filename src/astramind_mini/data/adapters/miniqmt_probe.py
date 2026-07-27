"""WSL adapter for the isolated Windows XtQuant market-data runner."""

from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic
from typing import Any

from ..application.identity import content_hash, schema_fingerprint
from ..contracts import (
    CapabilityState,
    ProbeReport,
    ProviderCapability,
    RawRecordEnvelope,
)


class MiniQMTCapabilityProbe:
    def __init__(
        self,
        *,
        runner: Path,
        python_command: str | None,
        xtquant_path: Path | None,
        quote_port: int | None,
        timeout_seconds: float,
        subscription_seconds: float = 3.0,
    ) -> None:
        self._runner = runner
        self._python_command = python_command
        self._xtquant_path = xtquant_path
        self._quote_port = quote_port
        self._timeout = timeout_seconds
        self._subscription_seconds = subscription_seconds

    async def probe(
        self,
    ) -> tuple[ProbeReport, tuple[tuple[RawRecordEnvelope, object], ...]]:
        probed_at = datetime.now(UTC)
        started = monotonic()
        try:
            windows_temp = Path("/mnt/c/Windows/Temp")
            with tempfile.TemporaryDirectory(
                prefix="astramind-miniqmt-",
                dir=windows_temp,
            ) as temporary_name:
                command = self._staged_command(Path(temporary_name))
                process = await asyncio.create_subprocess_exec(
                    *command,
                    cwd=windows_temp,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                try:
                    stdout, _stderr = await asyncio.wait_for(
                        process.communicate(),
                        timeout=self._timeout,
                    )
                except TimeoutError:
                    await _terminate_process_tree(process)
                    raise ProbeRunnerError("runner_timeout") from None
            if process.returncode != 0:
                body = _parse_body(stdout)
                raise ProbeRunnerError(str(body.get("runner_error_code", "runner_failed")))
            body = _parse_body(stdout)
            return self._build_result(body, probed_at, int((monotonic() - started) * 1000))
        except (OSError, ValueError, ProbeRunnerError) as error:
            code = error.code if isinstance(error, ProbeRunnerError) else "runner_unavailable"
            return self._failure_report(probed_at, code, int((monotonic() - started) * 1000))

    def _build_result(
        self,
        body: dict[str, Any],
        probed_at: datetime,
        total_latency_ms: int,
    ) -> tuple[ProbeReport, tuple[tuple[RawRecordEnvelope, object], ...]]:
        raw_capabilities = body.get("capabilities")
        if not isinstance(raw_capabilities, list) or not raw_capabilities:
            raise ProbeRunnerError("invalid_runner_response")
        capabilities = tuple(
            _capability(item, total_latency_ms)
            for item in raw_capabilities
            if isinstance(item, dict)
        )
        if not capabilities:
            raise ProbeRunnerError("invalid_runner_response")
        identity = {
            "provider": "miniqmt",
            "probed_at": probed_at,
            "capabilities": [item.model_dump(mode="json") for item in capabilities],
        }
        report = ProbeReport(
            probe_id=content_hash(identity),
            provider="miniqmt",
            gateway_version=str(body.get("gateway_version", "unknown")),
            client_version=str(body.get("client_version", "unknown")),
            probed_at=probed_at,
            capabilities=capabilities,
            known_gaps=tuple(
                item.capability_id
                for item in capabilities
                if item.state is not CapabilityState.AVAILABLE
            ),
        )
        records: list[tuple[RawRecordEnvelope, object]] = []
        raw_records = body.get("raw_records", [])
        if isinstance(raw_records, list):
            for item in raw_records:
                if not isinstance(item, dict) or "payload" not in item:
                    continue
                interface = str(item.get("interface_name", "unknown"))
                payload = item["payload"]
                request_identity = content_hash(
                    {"interface_name": interface, "probe_id": report.probe_id}
                )
                records.append(
                    (
                        RawRecordEnvelope(
                            provider="miniqmt",
                            interface_name=interface,
                            source_endpoint="windows-xtdata-local-rpc",
                            request_identity=request_identity,
                            received_at=probed_at,
                            schema_version="provider-v1",
                            content_hash=content_hash(payload),
                        ),
                        payload,
                    )
                )
        return report, tuple(records)

    def _failure_report(
        self,
        probed_at: datetime,
        code: str,
        latency_ms: int,
    ) -> tuple[ProbeReport, tuple[tuple[RawRecordEnvelope, object], ...]]:
        capability = ProviderCapability(
            capability_id="miniqmt:runner",
            interface_name="windows_xtdata_runner",
            state=CapabilityState.ERROR,
            interface_present=False,
            configured=self._python_command is not None or self._xtquant_path is not None,
            permission_available=None,
            data_available=False,
            latency_ms=latency_ms,
            error_code=code,
            known_gaps=(code,),
        )
        identity = {
            "provider": "miniqmt",
            "probed_at": probed_at,
            "capabilities": [capability.model_dump(mode="json")],
        }
        return (
            ProbeReport(
                probe_id=content_hash(identity),
                provider="miniqmt",
                gateway_version="wp-0002a-windows-runner-v1",
                client_version="unavailable",
                probed_at=probed_at,
                capabilities=(capability,),
                known_gaps=(code,),
            ),
            (),
        )

    def _staged_command(self, temporary: Path) -> list[str]:
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
        runner_path = self._windows_path(staged_runner)
        if self._python_command:
            interpreter = [self._python_command]
        else:
            interpreter = ["py", "-3.11" if python_path else "-3.12"]
        arguments = [
            *interpreter,
            runner_path,
            "--subscription-seconds",
            str(self._subscription_seconds),
        ]
        if python_path:
            arguments.extend(["--xtquant-path", python_path])
        if self._quote_port is not None:
            arguments.extend(["--quote-port", str(self._quote_port)])
        invocation = subprocess.list2cmdline(arguments)
        return [
            "/mnt/c/Windows/System32/cmd.exe",
            "/d",
            "/c",
            invocation,
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


class ProbeRunnerError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _parse_body(payload: bytes) -> dict[str, Any]:
    # The vendor client writes localized startup text using the Windows console
    # encoding before our ASCII-only JSON line.
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
    raise ProbeRunnerError("invalid_runner_json")


def _capability(payload: dict[str, Any], total_latency_ms: int) -> ProviderCapability:
    fields = payload.get("observed_fields", [])
    if not isinstance(fields, list):
        fields = []
    state = CapabilityState(str(payload.get("state", "error")))
    error_code = str(payload["error_code"]) if payload.get("error_code") else None
    raw_gaps = payload.get("known_gaps", [])
    if not isinstance(raw_gaps, list):
        raw_gaps = []
    if error_code and not raw_gaps:
        raw_gaps = [error_code]
    return ProviderCapability(
        capability_id=str(payload.get("capability_id", "miniqmt:unknown")),
        interface_name=str(payload.get("interface_name", "unknown")),
        state=state,
        interface_present=bool(payload.get("interface_present", False)),
        configured=bool(payload.get("configured", True)),
        permission_available=payload.get("permission_available"),
        data_available=bool(payload.get("data_available", False)),
        observed_fields=tuple(str(field) for field in fields),
        row_count=int(payload.get("row_count", 0)),
        latency_ms=total_latency_ms,
        schema_fingerprint=schema_fingerprint(fields) if fields else None,
        error_code=error_code,
        known_gaps=tuple(str(gap) for gap in raw_gaps),
    )


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


__all__ = ["MiniQMTCapabilityProbe"]
