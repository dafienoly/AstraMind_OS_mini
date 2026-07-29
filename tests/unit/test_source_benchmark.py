from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from astramind_mini.data.application.identity import content_hash
from astramind_mini.data.application.source_benchmark import benchmark_sources
from astramind_mini.data.contracts import (
    CanonicalDatasetRequest,
    ProviderBatch,
    SourceHealth,
    SourceHealthState,
)

NOW = datetime(2026, 7, 29, 8, tzinfo=UTC)


class BenchmarkSource:
    provider_id = "miniqmt"

    def __init__(self) -> None:
        self.calls = 0

    async def capabilities(self) -> frozenset[str]:
        return frozenset({"daily_market"})

    async def fetch(self, request: CanonicalDatasetRequest) -> ProviderBatch:
        self.calls += 1
        rows: tuple[dict[str, object], ...] = (
            {"instrument_id": "600519.SH", "trade_date": "20260728"},
        )
        return ProviderBatch(
            provider_id=self.provider_id,
            provider_version="test-v1",
            native_interface="daily",
            source_endpoint="fake",
            request_identity=content_hash({"request": request.model_dump(mode="json")}),
            retrieved_at=NOW,
            rows=rows,
            raw_payload=rows,
            completeness=1,
        )

    async def health(self) -> SourceHealth:
        return SourceHealth(
            provider_id=self.provider_id,
            provider_version="test-v1",
            state=SourceHealthState.HEALTHY,
            checked_at=NOW,
        )


def test_warm_benchmark_excludes_one_warmup_call_and_reports_percentiles() -> None:
    source = BenchmarkSource()
    request = CanonicalDatasetRequest(
        dataset_name="daily_market",
        as_of=NOW,
        universe=("600519.SH",),
    )

    report = asyncio.run(
        benchmark_sources(
            adapters={"miniqmt": source},
            requests=(request,),
            repetitions=3,
            cache_state="warm",
        )
    )

    assert source.calls == 4
    assert len(report.samples) == 3
    assert len(report.statistics) == 1
    assert report.statistics[0].sample_count == 3
    assert report.statistics[0].error_rate == 0
    assert report.statistics[0].throughput_rows_per_second > 0
