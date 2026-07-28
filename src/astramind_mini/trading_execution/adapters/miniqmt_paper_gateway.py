"""Authorized WSL bridge for idempotent MiniQMT Paper commands."""

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

from ..contracts.paper import PaperOrderIntent
from ..contracts.paper_canary import PaperCanaryAuthorization
from ..contracts.paper_continuous import (
    PaperBrokerCommandResult,
    PaperLimitProposal,
    PaperSubmissionApproval,
)
from ..domain.paper_continuous import validate_submission_approval
from ..domain.reconciliation import canonical_hash
from .miniqmt_account import MiniQMTAccountError, _parse_body, _terminate_process_tree


class MiniQMTPaperGateway:
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
        quote_port: int | None = None,
        timeout_seconds: float = 20,
    ) -> None:
        self._runner = runner
        self._python_command = python_command
        self._xtquant_path = xtquant_path
        self._userdata_path = userdata_path
        self._account_selector = account_selector
        self._account_mode = account_mode
        self._fingerprint_key = fingerprint_key
        self._quote_port = quote_port
        self._timeout = timeout_seconds

    async def query(self, intent: PaperOrderIntent) -> PaperBrokerCommandResult:
        return await self._command("query", intent)

    async def submit(
        self,
        *,
        intent: PaperOrderIntent,
        authorization: PaperCanaryAuthorization,
        proposal: PaperLimitProposal,
        approval: PaperSubmissionApproval,
        fresh_best_ask: float,
        quote_market_time: object,
        now: object,
    ) -> PaperBrokerCommandResult:
        if not isinstance(quote_market_time, datetime) or not isinstance(now, datetime):
            raise ValueError("Paper 提交时间必须带时区")
        validate_submission_approval(
            proposal=proposal,
            approval=approval,
            authorization=authorization,
            fresh_best_ask=fresh_best_ask,
            quote_market_time=quote_market_time,
            now=now,
        )
        if intent.instrument_id != authorization.instrument_id:
            raise ValueError("Paper 意图证券超出 StandingMandate")
        if (
            intent.quantity != authorization.quantity
            or intent.limit_price != approval.exact_limit_price
        ):
            raise ValueError("Paper 意图数量或限价超出最终批准")
        return await self._command("submit", intent)

    async def cancel(
        self,
        *,
        intent: PaperOrderIntent,
        approval: PaperSubmissionApproval,
    ) -> PaperBrokerCommandResult:
        if not approval.cancel_this_order_only:
            raise PermissionError("只允许撤销本次金丝雀订单")
        return await self._command("cancel", intent)

    async def _command(self, action: str, intent: PaperOrderIntent) -> PaperBrokerCommandResult:
        if self._account_mode != "simulation":
            raise MiniQMTAccountError("simulation_mode_required")
        body = await self._invoke(action, intent)
        payload = {
            "intent_id": intent.intent_id,
            "action": action,
            "outcome": _text(body, "outcome"),
            "broker_order_fingerprint": body.get("broker_order_fingerprint"),
            "broker_status_code": body.get("broker_status_code"),
            "cumulative_filled_quantity": _integer(body, "cumulative_filled_quantity"),
            "average_fill_price": body.get("average_fill_price"),
            "observed_at": _epoch(body, "observed_at_epoch"),
        }
        digest = canonical_hash(payload)
        return PaperBrokerCommandResult.model_validate(
            {
                "command_id": "paper-broker-command:" + digest[7:],
                "content_hash": digest,
                **payload,
            }
        )

    async def _invoke(self, action: str, intent: PaperOrderIntent) -> dict[str, Any]:
        windows_temp = Path("/mnt/c/Windows/Temp")
        with tempfile.TemporaryDirectory(prefix="astramind-paper-write-", dir=windows_temp) as name:
            temporary = Path(name)
            command = self._staged_command(temporary, action, intent)
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
                raise TimeoutError("paper_gateway_timeout") from None
            body = _parse_body(stdout)
            if process.returncode != 0 or body.get("runner_error_code"):
                raise MiniQMTAccountError("paper_gateway_failed")
            return body

    def _staged_command(self, temporary: Path, action: str, intent: PaperOrderIntent) -> list[str]:
        staged_runner = temporary / "runner.py"
        shutil.copyfile(self._runner, staged_runner)
        python_path = self._stage_xtquant(temporary)
        config = {
            "ASTRAMIND_MINIQMT_ACCOUNT_ID": self._account_selector,
            "ASTRAMIND_MINIQMT_ACCOUNT_MODE": self._account_mode,
            "ASTRAMIND_MINIQMT_USERDATA_PATH": self._userdata_path,
            "ASTRAMIND_MINIQMT_FINGERPRINT_KEY": self._fingerprint_key,
            "ASTRAMIND_MINIQMT_XTQUANT_PATH": python_path or None,
            "ASTRAMIND_MINIQMT_QUOTE_PORT": self._quote_port,
            "action": action,
            "order_remark": "am-" + intent.idempotency_key.rsplit("-", 1)[-1][:21],
            "instrument_id": intent.instrument_id,
            "side": intent.side,
            "quantity": intent.quantity,
            "limit_price": intent.limit_price,
            "required_cash_cny": round(intent.quantity * intent.limit_price + 10, 2),
        }
        config_path = temporary / "config.json"
        with config_path.open("x", encoding="utf-8") as stream:
            os.chmod(config_path, 0o600)
            json.dump(config, stream)
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


def _text(body: dict[str, Any], key: str) -> str:
    value = body.get(key)
    if not isinstance(value, str) or not value:
        raise MiniQMTAccountError("invalid_paper_gateway_payload")
    return value


def _integer(body: dict[str, Any], key: str) -> int:
    value = body.get(key)
    if not isinstance(value, int):
        raise MiniQMTAccountError("invalid_paper_gateway_payload")
    return value


def _epoch(body: dict[str, Any], key: str) -> datetime:
    value = body.get(key)
    if not isinstance(value, int | float):
        raise MiniQMTAccountError("invalid_paper_gateway_payload")
    return datetime.fromtimestamp(float(value), tz=UTC)


__all__ = ["MiniQMTPaperGateway"]
