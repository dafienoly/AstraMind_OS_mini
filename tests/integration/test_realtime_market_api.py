from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from fastapi.testclient import TestClient

from astramind_mini.composition import create_app
from astramind_mini.config import Settings
from astramind_mini.data.adapters.realtime_projection_store import RealtimeProjectionStore
from astramind_mini.data.application.identity import content_hash
from astramind_mini.data.contracts import RealtimeMarketProjection
from astramind_mini.data.contracts.realtime_projection import (
    RealtimeInstrumentProjection,
    RealtimeInstrumentQuote,
)
from astramind_mini.data.realtime_api import _instrument_events


def test_realtime_current_is_read_only_projection(tmp_path: Path) -> None:
    settings = Settings(
        environment="test",
        data_dir=tmp_path,
        control_db_path=tmp_path / "control.sqlite3",
        local_ops_db_path=tmp_path / "ops.sqlite3",
        shadow_db_path=tmp_path / "shadow.sqlite3",
    )
    client = TestClient(create_app(settings))

    assert client.get("/api/market/realtime").status_code == 404

    now = datetime.now(UTC)
    projection = RealtimeMarketProjection(
        projection_id=content_hash({"projection": "test"}),
        provider="miniqmt",
        session_id=content_hash({"session": "test"}),
        state="current",
        as_of=now,
        latest_received_at=now,
        granularity_ms=1000,
        quote_count=1,
        advancing=1,
        declining=0,
        unchanged=0,
        total_amount=1000,
    )
    RealtimeProjectionStore(tmp_path).publish_current(projection)

    response = client.get("/api/market/realtime")

    assert response.status_code == 200
    assert response.json()["provider"] == "miniqmt"
    assert response.json()["state"] == "current"


def test_disconnected_projection_is_not_relabelled_current_or_stale(
    tmp_path: Path,
) -> None:
    settings = Settings(
        environment="test",
        data_dir=tmp_path,
        control_db_path=tmp_path / "control.sqlite3",
        local_ops_db_path=tmp_path / "ops.sqlite3",
        shadow_db_path=tmp_path / "shadow.sqlite3",
    )
    now = datetime.now(UTC)
    projection = RealtimeMarketProjection(
        projection_id=content_hash({"projection": "disconnected"}),
        provider="miniqmt",
        session_id=content_hash({"session": "disconnected"}),
        state="disconnected",
        as_of=now,
        latest_received_at=now,
        granularity_ms=1000,
        quote_count=1,
        advancing=1,
        declining=0,
        unchanged=0,
        total_amount=1000,
    )
    RealtimeProjectionStore(tmp_path).publish_current(projection)

    response = TestClient(create_app(settings)).get("/api/market/realtime")

    assert response.status_code == 200
    assert response.json()["state"] == "disconnected"


def test_instrument_detail_and_local_watchlist_are_read_only_market_state(
    tmp_path: Path,
) -> None:
    settings = Settings(
        environment="test",
        data_dir=tmp_path / "data",
        control_db_path=tmp_path / "control.sqlite3",
        local_ops_db_path=tmp_path / "ops.sqlite3",
        shadow_db_path=tmp_path / "shadow.sqlite3",
    )
    now = datetime.now(UTC)
    session_id = content_hash({"session": "instrument-api"})
    projection = RealtimeInstrumentProjection(
        projection_id=content_hash({"projection": "instrument-api"}),
        provider="miniqmt",
        session_id=session_id,
        state="current",
        as_of=now,
        market_date=now.date(),
        quotes=(
            RealtimeInstrumentQuote(
                instrument_id="600000.SH",
                instrument_name="浦发银行",
                instrument_type="stock",
                received_at=now,
                last_price=10.5,
                status_label="正常交易",
            ),
        ),
    )
    RealtimeProjectionStore(settings.data_dir).publish_instruments(projection)
    client = TestClient(create_app(settings))

    response = client.get("/api/market/realtime/instruments/600000.SH")
    by_name = client.get("/api/market/realtime/instruments/search?q=浦发")
    by_code = client.get("/api/market/realtime/instruments/search?q=6000")
    saved = client.put(
        "/api/market/watchlist",
        json={"instrument_ids": ["600000.SH"]},
    )

    assert response.status_code == 200
    assert response.json()["quote"]["last_price"] == 10.5
    assert response.json()["minutes"] == []
    assert by_name.json()[0]["instrument_id"] == "600000.SH"
    assert by_code.json()[0]["instrument_name"] == "浦发银行"
    assert saved.status_code == 200
    assert client.get("/api/market/watchlist").json()["instrument_ids"] == ["600000.SH"]


def test_instrument_sse_does_not_block_the_api_event_loop() -> None:
    now = datetime.now(UTC)
    projection = RealtimeInstrumentProjection(
        projection_id=content_hash({"projection": "slow-sse"}),
        provider="miniqmt",
        session_id=content_hash({"session": "slow-sse"}),
        state="current",
        as_of=now,
        market_date=now.date(),
    )

    class SlowStore:
        def current_instruments(self) -> RealtimeInstrumentProjection:
            time.sleep(0.2)
            return projection

    async def exercise() -> tuple[bool, str]:
        stream = cast(
            AsyncGenerator[str, None],
            _instrument_events(
                cast(RealtimeProjectionStore, SlowStore()),
                frozenset(),
            ),
        )
        first: asyncio.Future[str] = asyncio.ensure_future(anext(stream))
        await asyncio.sleep(0.02)
        event_loop_remained_responsive = not first.done()
        payload = await first
        await stream.aclose()
        return event_loop_remained_responsive, payload

    responsive, payload = asyncio.run(exercise())

    assert responsive is True
    assert "event: instruments" in payload
