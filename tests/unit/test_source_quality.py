from __future__ import annotations

from datetime import UTC, datetime

from astramind_mini.data.application.identity import content_hash
from astramind_mini.data.application.source_quality import (
    compare_provider_batches,
    replacement_decision,
)
from astramind_mini.data.contracts import BenchmarkSample, ProviderBatch

NOW = datetime(2026, 7, 29, 6, tzinfo=UTC)


def batch(provider: str, rows: tuple[dict[str, object], ...]) -> ProviderBatch:
    return ProviderBatch(
        provider_id=provider,
        provider_version="v1",
        native_interface="daily",
        source_endpoint=provider,
        request_identity=content_hash({"provider": provider, "rows": rows}),
        retrieved_at=NOW,
        rows=rows,
        raw_payload=rows,
        completeness=1,
    )


def sample(provider: str, elapsed: float) -> BenchmarkSample:
    return BenchmarkSample(
        provider_id=provider,
        dataset_name="daily_market",
        cache_state="warm",
        row_count=100,
        total_ms=elapsed,
        fetch_ms=elapsed,
        normalize_ms=0,
        persist_ms=0,
    )


def test_replacement_requires_quality_and_two_times_speed() -> None:
    rows = (
        {
            "instrument_id": "600519.SH",
            "trade_date": "20260728",
            "open": 1400.0,
            "high": 1420.0,
            "low": 1390.0,
            "close": 1410.0,
            "volume": 100.0,
            "amount": 1_000_000.0,
        },
    )
    quality = compare_provider_batches(
        dataset_name="daily_market",
        candidate=batch("miniqmt", rows),
        reference=batch("tushare", rows),
        primary_key=("instrument_id", "trade_date"),
    )
    samples = tuple(
        [sample("miniqmt", 10) for _ in range(30)] + [sample("tushare", 25) for _ in range(30)]
    )

    decision = replacement_decision(
        dataset_name="daily_market",
        quality=quality,
        samples=samples,
    )

    assert quality.passed
    assert decision.replace
    assert decision.throughput_ratio == 2.5


def test_value_mismatch_blocks_replacement() -> None:
    reference = ({"instrument_id": "600519.SH", "trade_date": "20260728", "close": 1400.0},)
    candidate = ({"instrument_id": "600519.SH", "trade_date": "20260728", "close": 1300.0},)

    quality = compare_provider_batches(
        dataset_name="daily_market",
        candidate=batch("miniqmt", candidate),
        reference=batch("tushare", reference),
        primary_key=("instrument_id", "trade_date"),
    )

    assert not quality.passed
    assert quality.value_mismatches == 1
