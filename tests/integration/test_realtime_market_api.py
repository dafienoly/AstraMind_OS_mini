from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncGenerator
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import cast

from fastapi.testclient import TestClient

from astramind_mini.composition import create_app
from astramind_mini.config import Settings
from astramind_mini.data.adapters.realtime_projection_store import RealtimeProjectionStore
from astramind_mini.data.application.identity import content_hash
from astramind_mini.data.application.market_session_status import (
    SHANGHAI,
    MarketSessionContext,
)
from astramind_mini.data.contracts import RealtimeMarketProjection
from astramind_mini.data.contracts.realtime_projection import (
    RealtimeInstrumentProjection,
    RealtimeInstrumentQuote,
    RealtimeMinuteBar,
)
from astramind_mini.data.realtime_api import _freshness, _instrument_events


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
    assert response.json()["state"] == "stale"
    assert response.json()["operational_state"] == "unknown"


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
    assert response.json()["transport_health"] == "disconnected"


def test_api_freshness_distinguishes_lunch_close_and_daily_lag() -> None:
    context = MarketSessionContext(
        calendar_dates=(
            date(2026, 7, 28),
            date(2026, 7, 29),
            date(2026, 7, 30),
        ),
        open_dates=(
            date(2026, 7, 28),
            date(2026, 7, 29),
            date(2026, 7, 30),
        ),
        latest_completed_trade_date=date(2026, 7, 29),
    )
    lunch = datetime(2026, 7, 30, 12, tzinfo=SHANGHAI).astimezone(UTC)
    projection = RealtimeMarketProjection(
        projection_id=content_hash({"projection": "session-status"}),
        provider="miniqmt",
        session_id=content_hash({"session": "session-status"}),
        state="current",
        as_of=lunch,
        latest_received_at=lunch - timedelta(minutes=30),
        granularity_ms=1000,
        quote_count=1,
        advancing=1,
        declining=0,
        unchanged=0,
        total_amount=1000,
    )

    lunch_result = _freshness(projection, lunch, context=context)
    after_close = lunch.replace(hour=7, minute=30)
    close_result = _freshness(projection, after_close, context=context)

    assert lunch_result.operational_state == "lunch_break"
    assert lunch_result.state == "current"
    assert close_result.operational_state == "daily_lagging"
    assert close_result.daily_data_state == "lagging"
    assert close_result.latest_trading_date == date(2026, 7, 30)


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


def test_realtime_bar_window_aggregates_complete_session_buckets(tmp_path: Path) -> None:
    settings = Settings(
        environment="test",
        data_dir=tmp_path / "data",
        control_db_path=tmp_path / "control.sqlite3",
        local_ops_db_path=tmp_path / "ops.sqlite3",
        shadow_db_path=tmp_path / "shadow.sqlite3",
    )
    market_date = date(2026, 7, 30)
    start = datetime(2026, 7, 30, 9, 30, tzinfo=SHANGHAI)
    rows = tuple(
        RealtimeMinuteBar(
            provider="miniqmt",
            session_id=content_hash({"session": "bars"}),
            instrument_id="600000.SH",
            minute=start + timedelta(minutes=index),
            open=10 + index,
            high=10 + index,
            low=10 + index,
            close=10 + index,
            volume=1,
            amount=10 + index,
            observation_count=1,
            source_identity=content_hash({"minute": index}),
            lifecycle="sealed",
        )
        for index in range(15)
    )
    RealtimeProjectionStore(settings.data_dir).append_aggregate(
        kind="1m",
        market_date=market_date,
        rows=rows,
    )

    response = TestClient(create_app(settings)).get(
        "/api/market/realtime/instruments/600000.SH/bars",
        params={"frequency": 15, "recent_sessions": 5},
    )

    assert response.status_code == 200
    assert response.json()["sessions"] == ["2026-07-30"]
    assert len(response.json()["bars"]) == 1
    assert response.json()["bars"][0]["open"] == 10
    assert response.json()["bars"][0]["close"] == 24
    assert response.json()["indicator_state"] == "insufficient_seed"
    assert response.json()["known_gaps"] == []
