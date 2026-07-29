from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import TypedDict

import pytest

from astramind_mini.data.application.identity import content_hash
from astramind_mini.data.contracts import RealtimeQuoteObservation
from astramind_mini.data.etf_foundation.registry import ETF_CODES
from astramind_mini.data.etf_model_evidence.contracts import (
    EtfNavObservation,
    EtfOfficialBenchmarkObservation,
    EtfSpreadMinuteObservation,
    OfficialIndexDailyObservation,
)
from astramind_mini.data.etf_model_evidence.gates import evaluate_etf_model_gate
from astramind_mini.data.etf_model_evidence.normalization import (
    normalize_nav,
    normalize_official_benchmarks,
)
from astramind_mini.data.etf_model_evidence.spread import (
    EtfSpreadMinuteProjector,
    EtfSpreadMinuteStore,
)
from astramind_mini.data.ports import ProviderTable

HASH = "sha256:" + "1" * 64
SESSION = "sha256:" + "2" * 64
NOW = datetime(2026, 7, 29, 8, tzinfo=UTC)


class SourceFields(TypedDict):
    provider: str
    source_endpoint: str
    retrieved_at: datetime
    available_at: datetime
    schema_version: str
    source_record_hash: str


def test_official_mapping_requires_complete_unambiguous_provider_identity() -> None:
    table = _table(
        "etf_basic",
        tuple(
            {
                "ts_code": code,
                "index_code": f"I{position:06d}.CSI",
                "index_name": f"指数{position}",
            }
            for position, code in enumerate(ETF_CODES)
        ),
    )
    rows = normalize_official_benchmarks(table)
    assert len(rows) == len(ETF_CODES)
    assert all(not row.historical_availability_known for row in rows)
    assert all(row.effective_from == date(2026, 7, 29) for row in rows)

    with pytest.raises(ValueError, match="未覆盖白名单"):
        normalize_official_benchmarks(
            _table("etf_basic", tuple(table.rows[:-1])),
        )


def test_nav_uses_announcement_date_and_rejects_unknown_availability() -> None:
    code = ETF_CODES[0]
    row = normalize_nav(
        _table(
            "fund_nav",
            (
                {
                    "ts_code": code,
                    "nav_date": "20260728",
                    "ann_date": "20260729",
                    "unit_nav": 1.2,
                    "accum_nav": 1.5,
                    "adj_nav": 1.3,
                },
            ),
        )
    )[0]
    assert row.available_at.date() == date(2026, 7, 29)
    assert row.nav_date == date(2026, 7, 28)

    with pytest.raises(ValueError, match="缺少公告日"):
        normalize_nav(
            _table(
                "fund_nav",
                (
                    {
                        "ts_code": code,
                        "nav_date": "20260728",
                        "unit_nav": 1.2,
                    },
                ),
            )
        )


def test_spread_projector_ignores_invalid_quotes_and_store_is_replayable(
    tmp_path: Path,
) -> None:
    code = ETF_CODES[0]
    projector = EtfSpreadMinuteProjector(
        feed_session_id=SESSION,
        market_date=date(2026, 7, 29),
        universe=(code,),
    )
    projector.ingest(
        (
            _quote(code, datetime(2026, 7, 29, 1, 30, 10, tzinfo=UTC), 1.0, 1.002),
            _quote(code, datetime(2026, 7, 29, 1, 30, 20, tzinfo=UTC), 1.01, 1.009),
        )
    )
    rows = projector.drain_closed(datetime(2026, 7, 29, 1, 31, tzinfo=UTC))
    assert len(rows) == 1
    assert rows[0].quote_count == 2
    assert rows[0].valid_quote_count == 1
    assert rows[0].quoted_spread_bps_median == pytest.approx(19.98001998)

    store = EtfSpreadMinuteStore(tmp_path)
    assert store.append(rows) is not None
    assert store.load_dates((date(2026, 7, 29),)) == rows


def test_etf_gate_passes_only_after_exact_60_session_forward_window() -> None:
    code = ETF_CODES[0]
    sessions = _weekdays(date(2026, 7, 30), 60)
    mapping = _mapping(code, sessions[0])
    nav = tuple(_nav(code, day) for day in sessions)
    indexes = tuple(_index(mapping.benchmark_code, day) for day in sessions)
    spreads = _spread_window(code, sessions, 10.0, 20.0)
    gate = evaluate_etf_model_gate(
        instrument_id=code,
        evidence_cutoff=sessions[-1],
        open_dates=sessions,
        mappings=(mapping,),
        index_daily=indexes,
        nav_rows=nav,
        etf_trade_dates=sessions,
        spread_rows=spreads,
        evaluated_at=NOW + timedelta(days=100),
    )
    assert gate.ready
    assert gate.qualifying_spread_session_count == 54
    assert gate.spread_median_bps == 10.0
    assert gate.spread_p90_bps == 20.0


def test_etf_gate_does_not_backcast_current_mapping_or_short_spread_history() -> None:
    code = ETF_CODES[0]
    sessions = _weekdays(date(2026, 6, 1), 60)
    mapping = _mapping(code, date(2026, 7, 29))
    gate = evaluate_etf_model_gate(
        instrument_id=code,
        evidence_cutoff=sessions[-1],
        open_dates=sessions,
        mappings=(mapping,),
        index_daily=tuple(_index(mapping.benchmark_code, day) for day in sessions),
        nav_rows=tuple(_nav(code, day) for day in sessions),
        etf_trade_dates=sessions,
        spread_rows=(),
        evaluated_at=NOW,
    )
    assert not gate.ready
    assert gate.mapping_status == "pending"
    assert gate.spread_status == "pending"
    assert "official_benchmark_mapping_window_not_point_in_time" in gate.reason_codes
    assert "spread_session_coverage_below_90pct" in gate.reason_codes


def _table(api_name: str, rows: tuple[dict[str, object], ...]) -> ProviderTable:
    return ProviderTable(
        api_name=api_name,
        fields=tuple(rows[0]) if rows else (),
        rows=rows,
        raw_body={"code": 0, "data": {"fields": [], "items": []}},
        request_identity=HASH,
        received_at=NOW,
        source_endpoint="https://example.test/api",
    )


def _quote(
    code: str,
    market_time: datetime,
    bid: float,
    ask: float,
) -> RealtimeQuoteObservation:
    return RealtimeQuoteObservation(
        instrument_id=code,
        market_time_ms=int(market_time.timestamp() * 1000),
        received_at=market_time,
        bid_prices=(bid,),
        ask_prices=(ask,),
        raw_content_hash=content_hash((code, market_time, bid, ask)),
    )


def _mapping(code: str, effective: date) -> EtfOfficialBenchmarkObservation:
    return EtfOfficialBenchmarkObservation(
        **_source(),
        instrument_id=code,
        benchmark_code="000001.CSI",
        benchmark_name="官方指数",
        effective_from=effective,
        historical_availability_known=False,
        evidence_kind="provider_current_registry",
    )


def _nav(code: str, day: date) -> EtfNavObservation:
    return EtfNavObservation(
        **_source(day),
        instrument_id=code,
        nav_date=day,
        announced_on=day,
        unit_nav=1.0,
    )


def _index(code: str, day: date) -> OfficialIndexDailyObservation:
    return OfficialIndexDailyObservation(
        **_source(day),
        index_code=code,
        trade_date=day,
        open=100.0,
        high=101.0,
        low=99.0,
        close=100.0,
        previous_close=100.0,
        change=0.0,
        percent_change=0.0,
    )


def _source(day: date = date(2026, 7, 29)) -> SourceFields:
    available = datetime.combine(day, time(10), tzinfo=UTC)
    return {
        "provider": "test",
        "source_endpoint": "test",
        "retrieved_at": NOW,
        "available_at": available,
        "schema_version": "1.0.0",
        "source_record_hash": HASH,
    }


def _weekdays(start: date, count: int) -> tuple[date, ...]:
    result: list[date] = []
    day = start
    while len(result) < count:
        if day.weekday() < 5:
            result.append(day)
        day += timedelta(days=1)
    return tuple(result)


def _spread_window(
    code: str,
    sessions: tuple[date, ...],
    median_bps: float,
    p90_bps: float,
) -> tuple[EtfSpreadMinuteObservation, ...]:
    rows = []
    for day in sessions[:54]:
        for offset in range(216):
            minute = datetime.combine(day, time(9, 30), tzinfo=UTC) + timedelta(minutes=offset)
            rows.append(
                EtfSpreadMinuteObservation(
                    provider="miniqmt",
                    feed_session_id=SESSION,
                    instrument_id=code,
                    market_date=day,
                    minute=minute,
                    first_market_time=minute,
                    last_market_time=minute,
                    quote_count=1,
                    valid_quote_count=1,
                    quoted_spread_bps_median=median_bps,
                    quoted_spread_bps_p90=p90_bps,
                    available_at=minute,
                    source_content_hash=HASH,
                    schema_version="v1",
                )
            )
    return tuple(rows)
