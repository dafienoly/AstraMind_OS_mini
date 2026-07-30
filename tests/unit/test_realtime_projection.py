from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from astramind_mini.data.adapters.realtime_projection_store import RealtimeProjectionStore
from astramind_mini.data.application.identity import canonical_json, content_hash
from astramind_mini.data.application.realtime_projection import RealtimeQuoteProjector
from astramind_mini.data.contracts import (
    RealtimeInstrumentProjection,
    RealtimeQuoteObservation,
)


def quote(
    instrument: str,
    received_at: datetime,
    *,
    price: float,
    previous: float = 10,
    volume: float = 100,
    amount: float = 1000,
) -> RealtimeQuoteObservation:
    return RealtimeQuoteObservation(
        instrument_id=instrument,
        market_time_ms=int(received_at.timestamp() * 1000),
        received_at=received_at,
        last_price=price,
        previous_close=previous,
        volume=volume,
        amount=amount,
        raw_content_hash=content_hash(
            {"instrument": instrument, "received_at": received_at, "price": price}
        ),
    )


def test_projection_builds_breadth_industry_and_closed_minute() -> None:
    started = datetime(2026, 7, 29, 1, 30, 10, tzinfo=UTC)
    session_id = content_hash({"session": "test"})
    projector = RealtimeQuoteProjector(
        session_id=session_id,
        industry_membership={"600000.SH": "801780.SI", "000001.SZ": "801780.SI"},
        breadth_universe=frozenset({"600000.SH", "000001.SZ"}),
    )
    projector.ingest(
        (
            quote("600000.SH", started, price=11),
            quote("000001.SZ", started, price=9),
            quote("000300.SH", started, price=4000, previous=3990),
        )
    )

    projection = projector.project(started + timedelta(seconds=1))

    assert projection.advancing == 1
    assert projection.declining == 1
    assert projection.quote_count == 3
    assert projection.breadth_observed == 2
    assert projection.breadth_expected == 2
    assert projection.breadth_coverage_ratio == 1
    assert projection.industries[0].observed_constituents == 2
    assert projection.indexes[0].instrument_id == "000300.SH"

    projector.ingest(
        (
            quote(
                "600000.SH",
                started.replace(second=20),
                price=11.5,
                volume=120,
                amount=1300,
            ),
        )
    )
    projector.ingest(
        (
            quote(
                "600000.SH",
                started.replace(minute=31),
                price=12,
                volume=150,
                amount=1600,
            ),
        )
    )
    bars = projector.drain_closed_minutes()
    assert len(bars) == 1
    assert bars[0].open == bars[0].close == 11.5
    assert bars[0].volume == 20


def test_projection_flushes_last_open_minute_at_session_end() -> None:
    started = datetime(2026, 7, 29, 1, 30, 10, tzinfo=UTC)
    projector = RealtimeQuoteProjector(session_id=content_hash({"session": "flush"}))
    projector.ingest((quote("600000.SH", started, price=11),))
    projector.ingest(
        (
            quote(
                "600000.SH",
                started.replace(second=20),
                price=11.1,
                volume=110,
                amount=1100,
            ),
        )
    )

    bars = projector.close_open_minutes()

    assert len(bars) == 1
    assert bars[0].instrument_id == "600000.SH"
    assert bars[0].minute.hour == 9
    assert bars[0].minute.minute == 30
    assert projector.close_open_minutes() == ()


def test_projection_does_not_create_bar_from_initial_or_unchanged_snapshot() -> None:
    started = datetime(2026, 7, 29, 1, 30, 10, tzinfo=UTC)
    projector = RealtimeQuoteProjector(session_id=content_hash({"session": "no-trade"}))
    projector.ingest((quote("600000.SH", started, price=11),))
    projector.ingest(
        (
            quote(
                "600000.SH",
                started.replace(second=20),
                price=11,
                volume=100,
                amount=1000,
            ),
        )
    )

    assert projector.close_open_minutes() == ()


def test_projection_store_reuses_unchanged_instrument_projection(tmp_path: Path) -> None:
    now = datetime.now(UTC)
    store = RealtimeProjectionStore(tmp_path)
    projection = RealtimeInstrumentProjection(
        projection_id=content_hash({"projection": "cache"}),
        provider="miniqmt",
        session_id=content_hash({"session": "cache"}),
        state="current",
        as_of=now,
        market_date=now.date(),
    )
    store.publish_instruments(projection)

    first = store.current_instruments()
    second = store.current_instruments()

    assert first is second


def test_instrument_projection_keeps_book_status_limits_and_forming_minute() -> None:
    started = datetime(2026, 7, 29, 1, 30, 10, tzinfo=UTC)
    projector = RealtimeQuoteProjector(
        session_id=content_hash({"session": "instrument"}),
        instrument_names={"600000.SH": "浦发银行"},
        instrument_types={"600000.SH": "stock"},
        price_limits={"600000.SH": (12.1, 9.9)},
    )
    initial = quote("600000.SH", started, price=11)
    projector.ingest(
        (
            initial.model_copy(
                update={
                    "bid_prices": (10.99, 10.98),
                    "ask_prices": (11.01, 11.02),
                    "bid_volumes": (1000.0, 800.0),
                    "ask_volumes": (900.0, 700.0),
                    "stock_status": 0,
                }
            ),
        )
    )
    projector.ingest(
        (
            quote(
                "600000.SH",
                started.replace(second=20),
                price=11.01,
                volume=120,
                amount=1300,
            ).model_copy(
                update={
                    "bid_prices": (11.0,),
                    "ask_prices": (11.02,),
                    "bid_volumes": (1100.0,),
                    "ask_volumes": (950.0,),
                    "stock_status": 0,
                }
            ),
        )
    )

    projection = projector.instrument_projection(started.replace(second=21))

    assert projection.state == "current"
    assert projection.quotes[0].instrument_name == "浦发银行"
    assert projection.quotes[0].upper_limit == 12.1
    assert projection.quotes[0].status_label == "正常交易"
    assert len(projection.quotes[0].bids) == 5
    assert projection.open_minutes[0].close == 11.01


def test_cumulative_counter_reset_is_explicit_not_silently_clamped() -> None:
    started = datetime(2026, 7, 30, 1, 30, 10, tzinfo=UTC)
    projector = RealtimeQuoteProjector(
        session_id=content_hash({"session": "reset"}),
        instrument_types={"600000.SH": "stock"},
    )
    projector.ingest((quote("600000.SH", started, price=10, volume=100, amount=1000),))
    projector.ingest(
        (
            quote(
                "600000.SH",
                started.replace(second=20),
                price=10.1,
                volume=0,
                amount=0,
            ),
        )
    )

    forming = projector.instrument_projection(started.replace(second=21)).open_minutes[0]

    assert forming.volume == 0
    assert forming.amount == 0
    assert forming.known_gaps == ("cumulative_counter_reset",)
    assert forming.is_complete is False
    assert forming.counter_epoch == 1


def test_short_capture_does_not_close_current_incomplete_minute() -> None:
    started = datetime(2026, 7, 30, 1, 30, 10, tzinfo=UTC)
    projector = RealtimeQuoteProjector(
        session_id=content_hash({"session": "short-capture"}),
        instrument_types={"600000.SH": "stock"},
    )
    projector.ingest((quote("600000.SH", started, price=10, volume=100, amount=1000),))
    projector.ingest(
        (
            quote(
                "600000.SH",
                started.replace(second=20),
                price=10.1,
                volume=110,
                amount=1101,
            ),
        )
    )

    assert projector.close_completed_minutes(started.replace(second=40)) == ()
    forming = projector.instrument_projection(started.replace(second=40)).open_minutes
    assert len(forming) == 1
    assert forming[0].lifecycle == "forming"
    sealed = projector.close_completed_minutes(started.replace(minute=31, second=0))
    assert len(sealed) == 1
    assert sealed[0].lifecycle == "closed"
    assert sealed[0].is_complete is True


def test_raw_retention_requires_verified_aggregation(tmp_path: Path) -> None:
    store = RealtimeProjectionStore(tmp_path)
    session_id = content_hash({"session": "old"})
    directory = tmp_path / "realtime" / "miniqmt" / "sessions" / session_id.rsplit(":", 1)[-1]
    directory.mkdir(parents=True)
    (directory / "session.json").write_bytes(
        canonical_json(
            {
                "session_id": session_id,
                "market_date": "2026-07-20",
                "subscribed_at": "2026-07-20T01:30:00+00:00",
            }
        )
    )
    raw = directory / "batch.raw.json.gz"
    normalized = directory / "batch.normalized.json.gz"
    raw.write_bytes(b"raw")
    normalized.write_bytes(b"normalized")

    assert store.prune_raw_payloads(retained_dates=frozenset()) == ()
    (directory / "aggregation-verified.json").write_text("{}", encoding="utf-8")

    removed = store.prune_raw_payloads(
        retained_dates=frozenset({date(2026, 7, 28), date(2026, 7, 29)})
    )

    assert removed == ()
    assert raw.exists()
    assert normalized.exists()
    assert not (directory / "raw-retention-tombstone.json").exists()


def test_retention_requires_minute_aggregation_evidence(tmp_path: Path) -> None:
    store = RealtimeProjectionStore(tmp_path)
    session_id = content_hash({"session": "wrong-kind"})
    second_path = (
        tmp_path
        / "realtime"
        / "miniqmt"
        / "aggregates"
        / "1s"
        / "2026-07-20"
        / "projection.json.gz"
    )
    second_path.parent.mkdir(parents=True)
    second_path.write_bytes(b"projection")
    try:
        store.verify_session_aggregation(
            session_id=session_id,
            aggregate_paths=(second_path,),
        )
    except ValueError as error:
        assert "只能使用 1 分钟聚合证据" in str(error)
    else:
        raise AssertionError("一秒聚合不得作为细粒度留存清理证据")
