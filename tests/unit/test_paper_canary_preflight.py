from __future__ import annotations

import asyncio
import importlib.util
import sqlite3
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from astramind_mini.config import Settings
from astramind_mini.paper_canary_preflight import PaperCanaryPreflight
from astramind_mini.trading_execution.adapters.miniqmt_account import MiniQMTAccountError
from astramind_mini.trading_execution.adapters.miniqmt_account_normalization import (
    build_account_snapshot,
)
from astramind_mini.trading_execution.adapters.miniqmt_canary_quote import (
    CanaryQuote,
    MiniQMTCanaryQuoteReader,
)
from astramind_mini.trading_execution.adapters.paper_canary_store import (
    PaperCanaryAuthorizationStore,
)
from astramind_mini.trading_execution.adapters.windows_runner_diagnostics import (
    classify_runner_failure,
    record_runner_diagnostic,
)
from astramind_mini.trading_execution.domain import (
    build_callback_handshake,
    build_mode_lock,
    build_paper_account_baseline,
    build_paper_canary_authorization,
)

SHANGHAI = timezone(timedelta(hours=8))
NOW = datetime(2026, 7, 29, 9, 36, tzinfo=SHANGHAI)


def _evidence() -> Any:
    snapshot = build_account_snapshot(
        account_mode="simulation",
        account_fingerprint="sha256:" + "c" * 64,
        as_of=NOW,
        asset={
            "cash_cny": 20_000,
            "frozen_cash_cny": 0,
            "market_value_cny": 0,
            "total_asset_cny": 20_000,
        },
        positions=[],
        orders=[],
        trades=[],
        client_version="test",
        gateway_version="test",
    )
    lock = build_mode_lock(
        configured_mode="simulation",
        broker_account_matched=True,
        broker_account_type=2,
        broker_account_classification=1,
        broker_account_status=0,
        client_version="test",
        gateway_version="test",
        verified_at=NOW,
    )
    handshake = build_callback_handshake(
        mode_lock=lock,
        snapshot=snapshot,
        subscribed=True,
        unsubscribed=True,
        callback_types=(),
        callback_count=0,
        foreign_account_callback_count=0,
        disconnected=False,
        started_at=NOW,
        completed_at=NOW,
    )
    return build_paper_account_baseline(snapshot, lock, handshake, created_at=NOW)


def _authorization(baseline_id: str) -> Any:
    return build_paper_canary_authorization(
        source_portfolio_target_id="portfolio-target:approved",
        source_shadow_order_plan_id="order-plan:shadow",
        account_baseline_id=baseline_id,
        instrument_id="605208.SH",
        quantity=100,
        max_notional_cny=50_000,
        mandate_start=NOW.replace(hour=9, minute=30),
        mandate_end=NOW.replace(hour=10, minute=0),
        submission_start=NOW.replace(hour=9, minute=35),
        submission_end=NOW.replace(hour=9, minute=45),
        approved_at=NOW - timedelta(days=1),
    )


def _quote(*, age_seconds: float = 1) -> CanaryQuote:
    return CanaryQuote(
        instrument_id="605208.SH",
        best_ask=12.34,
        last_close=12.0,
        limit_up=13.2,
        risk_warning=False,
        listed_long_enough=True,
        instrument_detail_available=True,
        market_time=NOW - timedelta(seconds=age_seconds),
        received_at=NOW,
    )


def _preflight(tmp_path: Path, quote: CanaryQuote) -> PaperCanaryPreflight:
    database = tmp_path / "shadow.sqlite3"
    baseline = _evidence()
    PaperCanaryAuthorizationStore(database).publish(_authorization(baseline.baseline_id))

    async def startup(_: Settings) -> Any:
        return SimpleNamespace(account_baseline=baseline)

    class Quotes:
        async def read(self, instrument_id: str) -> CanaryQuote:
            assert instrument_id == "605208.SH"
            return quote

    return PaperCanaryPreflight(
        Settings(environment="test", shadow_db_path=database),
        clock=lambda: NOW,
        startup=startup,
        quotes=lambda _: Quotes(),  # type: ignore[arg-type,return-value]
    )


def test_preflight_is_read_only_and_broker_writes_remain_zero(tmp_path: Path) -> None:
    preflight = _preflight(tmp_path, _quote())
    result = asyncio.run(preflight.run())

    assert result.window_state == "open"
    assert result.broker_write_attempts == 0
    with sqlite3.connect(tmp_path / "shadow.sqlite3") as connection:
        assert connection.execute("SELECT count(*) FROM paper_limit_proposals").fetchone() == (0,)
        assert connection.execute("SELECT count(*) FROM paper_order_intents").fetchone() == (0,)
        assert connection.execute("SELECT count(*) FROM paper_broker_commands").fetchone() == (0,)


def test_preflight_rejects_stale_quote_without_creating_proposal(tmp_path: Path) -> None:
    preflight = _preflight(tmp_path, _quote(age_seconds=3.001))
    with pytest.raises(MiniQMTAccountError, match="canary_quote_stale"):
        asyncio.run(preflight.run())

    with sqlite3.connect(tmp_path / "shadow.sqlite3") as connection:
        assert connection.execute("SELECT count(*) FROM paper_limit_proposals").fetchone() == (0,)


def test_runner_failure_categories_and_redacted_stream_retention(tmp_path: Path) -> None:
    stderr = (
        b"WSL ERROR: UtilAcceptVsock C:\\Users\\private\\qmt "
        b"account_id=test-placeholder token=dummy"
    )
    assert (
        classify_runner_failure(
            stdout=b"",
            stderr=stderr,
            body=None,
            default="invalid_runner_json",
        )
        == "windows_interop_unavailable"
    )
    assert (
        classify_runner_failure(
            stdout=b'{"runner_error_code":"qmt_not_connected"}',
            stderr=b"",
            body={"runner_error_code": "qmt_not_connected"},
            default="canary_quote_failed",
        )
        == "qmt_not_connected"
    )
    assert (
        classify_runner_failure(
            stdout=b"not-json",
            stderr=b"",
            body=None,
            default="invalid_runner_json",
        )
        == "invalid_runner_json"
    )
    target = record_runner_diagnostic(
        root=tmp_path,
        runner="canary-quote",
        stdout=b"/home/private/work account_id=test-placeholder",
        stderr=stderr,
        returncode=1,
        outcome="windows_interop_unavailable",
        secrets=("test-placeholder", "dummy"),
    )
    assert target is not None
    retained = target.read_text(encoding="utf-8")
    assert "windows_interop_unavailable" in retained
    assert "UtilAcceptVsock" in retained
    assert "private" not in retained
    assert "test-placeholder" not in retained
    assert "dummy" not in retained


def test_quote_reader_timeout_is_distinct(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import astramind_mini.trading_execution.adapters.miniqmt_canary_quote as module

    class Process:
        returncode: int | None = None
        pid = None

        async def communicate(self) -> tuple[bytes, bytes]:
            await asyncio.sleep(1)
            return b"", b""

    async def create(*_: object, **__: object) -> Process:
        return Process()

    async def terminate(_: object) -> None:
        return None

    reader = MiniQMTCanaryQuoteReader(
        runner=tmp_path / "unused.py",
        python_command=None,
        xtquant_path=None,
        quote_port=None,
        timeout_seconds=0.001,
        diagnostic_root=tmp_path / "diagnostics",
    )
    monkeypatch.setattr(reader, "_command", lambda *_: ["unused"])
    monkeypatch.setattr(
        "astramind_mini.trading_execution.adapters.miniqmt_canary_quote."
        "asyncio.create_subprocess_exec",
        create,
    )
    monkeypatch.setattr(module, "_terminate_process_tree", terminate)
    with pytest.raises(MiniQMTAccountError, match="canary_quote_timeout"):
        asyncio.run(reader._invoke("605208.SH"))


def test_windows_runner_waits_for_a_new_fresh_tick(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = Path("scripts/windows/miniqmt_canary_quote.py")
    spec = importlib.util.spec_from_file_location("canary_quote_runner_test", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    now_ms = int(time.time() * 1000)
    ticks = [
        {"time": now_ms - 4_000, "askPrice": [12.34], "lastClose": 12.0},
        {"time": now_ms - 1_000, "askPrice": [12.34], "lastClose": 12.0},
    ]

    class XtData:
        @staticmethod
        def get_full_tick(_: list[str]) -> dict[str, object]:
            return {"605208.SH": ticks.pop(0)}

        @staticmethod
        def get_instrument_detail(*_: object) -> dict[str, object]:
            return {"InstrumentName": "test", "OpenDate": "20200101"}

    monkeypatch.setattr(module.importlib, "import_module", lambda _: XtData())
    result = module.run("605208.SH", None, None, fresh_wait_seconds=1)
    assert result["sample_count"] == 2
    assert result["new_tick_observed"] is True


def test_preflight_interrupt_never_reports_a_broker_write(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import scripts.preflight_paper_canary as command

    def interrupt(coroutine: Any) -> None:
        coroutine.close()
        raise KeyboardInterrupt

    monkeypatch.setattr(sys, "argv", ["preflight_paper_canary.py"])
    monkeypatch.setattr(
        "scripts.preflight_paper_canary.asyncio.run",
        interrupt,
    )
    assert command.main() == 130
    output = capsys.readouterr().out
    assert "state=interrupted" in output
    assert "broker_write_attempts=0" in output
