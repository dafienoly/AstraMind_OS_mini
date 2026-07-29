"""MiniQMT L1 normalization, persistence, and source-boundary proof."""

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from astramind_mini.data.adapters.miniqmt_l1 import (
    MiniQMTL1Capture,
    normalize_l1_messages,
    quote_is_stale,
)
from astramind_mini.data.adapters.realtime_store import RealtimeMicroBatchStore
from astramind_mini.data.application.identity import content_hash
from astramind_mini.data.contracts import FeedSessionReport, FeedSessionState


def _report(now: datetime) -> FeedSessionReport:
    return FeedSessionReport(
        session_id=content_hash({"session": "fixture"}),
        provider="miniqmt",
        client_version="fixture-v1",
        state=FeedSessionState.COMPLETE,
        markets=("SH", "SZ"),
        subscribed_at=now,
        ended_at=now,
        microbatch_ids=(),
        received_messages=2,
        duplicate_messages=1,
        disconnects=0,
    )


def test_l1_messages_are_deduplicated_and_normalized() -> None:
    now = datetime(2026, 7, 27, 1, tzinfo=UTC)
    message = {
        "000001.SZ": {
            "time": 1_700_000_000_000,
            "lastPrice": 10.2,
            "open": 10.0,
            "high": 10.3,
            "low": 9.9,
            "volume": 100,
            "amount": 1020,
        }
    }
    observations, duplicates = normalize_l1_messages([message, message], now)
    assert len(observations) == 1
    assert duplicates == 1
    assert observations[0].last_price == 10.2
    assert quote_is_stale(observations[0], now=now + timedelta(seconds=11))


def test_microbatch_is_immutable_and_conflicts_fail_closed(tmp_path: Path) -> None:
    now = datetime(2026, 7, 27, 1, tzinfo=UTC)
    raw = [{"000001.SZ": {"time": 1, "lastPrice": 10.2}}]
    observations, _ = normalize_l1_messages(raw, now)
    store = RealtimeMicroBatchStore(tmp_path)
    batch, manifest = store.append(_report(now), raw, observations)
    repeated, _ = store.append(_report(now), raw, observations)
    assert repeated == batch
    assert manifest.is_file()
    with pytest.raises(ValueError, match="身份冲突"):
        store.append(_report(now), [{"changed": True}], observations)


def test_windows_runner_contains_only_market_data_surface() -> None:
    source = Path("scripts/windows/miniqmt_l1_capture.py").read_text(encoding="utf-8").lower()
    forbidden = (
        "xtquanttrader",
        "order_stock",
        "cancel_order",
        "query_stock_asset",
        "query_stock_position",
    )
    assert "subscribe_whole_quote" in source
    assert "unsubscribe_quote" in source
    assert not any(token in source for token in forbidden)


def test_persistent_data_bridge_contains_no_trading_surface() -> None:
    source = Path("scripts/windows/miniqmt_data_bridge.py").read_text(encoding="utf-8").lower()
    forbidden = (
        "xtquanttrader",
        "order_stock",
        "cancel_order_stock",
        "query_stock_asset",
        "query_stock_position",
        "query_stock_order",
        "query_stock_trade",
    )
    assert not any(token in source for token in forbidden)
    assert 'import_module("xtquant.xtdata")' in source


def test_capture_reconnects_after_a_disconnected_runner(tmp_path: Path) -> None:
    class FixtureCapture(MiniQMTL1Capture):
        calls = 0

        async def _invoke(self, markets: tuple[str, ...], seconds: float) -> dict[str, Any]:
            self.calls += 1
            if self.calls == 1:
                return {"runner_error_code": "fixture_disconnected"}
            return {
                "client_version": "fixture-v1",
                "subscribed": True,
                "unsubscribed": True,
                "messages": [],
            }

    capture = FixtureCapture(
        runner=tmp_path / "unused.py",
        python_command=None,
        xtquant_path=None,
        quote_port=None,
    )
    report, _, _ = asyncio.run(capture.capture(seconds=0.5))
    assert report.disconnects == 1
    assert report.state is FeedSessionState.EMPTY
