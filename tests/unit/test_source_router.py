from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from astramind_mini.data.adapters import DuckDBParquetEncoder, RoutedHistoricalProvider
from astramind_mini.data.adapters.filesystem import FilesystemRawRecordStore
from astramind_mini.data.application.daily_pipeline_collection import collect_calendar
from astramind_mini.data.application.identity import content_hash
from astramind_mini.data.application.source_router import (
    DatasetSourceRouter,
    SourceRouteError,
)
from astramind_mini.data.contracts import (
    CanonicalDatasetRequest,
    DatasetSourceRoute,
    ProviderBatch,
    SourceHealth,
    SourceHealthState,
    SourceProviderEpoch,
)

NOW = datetime(2026, 7, 29, 6, tzinfo=UTC)


class FakeSource:
    def __init__(
        self,
        provider_id: str,
        rows: tuple[dict[str, object], ...],
        *,
        completeness: float | None = None,
    ) -> None:
        self.provider_id = provider_id
        self.rows = rows
        self.completeness = completeness
        self.calls = 0
        self.requests: list[CanonicalDatasetRequest] = []

    async def capabilities(self) -> frozenset[str]:
        return frozenset({"daily_market"})

    async def fetch(self, request: CanonicalDatasetRequest) -> ProviderBatch:
        self.calls += 1
        self.requests.append(request)
        return ProviderBatch(
            provider_id=self.provider_id,
            provider_version="test-v1",
            native_interface="daily",
            source_endpoint=f"fake-{self.provider_id}",
            request_identity=content_hash(
                {"provider": self.provider_id, "request": request.model_dump(mode="json")}
            ),
            retrieved_at=NOW,
            rows=self.rows,
            raw_payload={"rows": self.rows},
            completeness=(
                self.completeness if self.completeness is not None else (1 if self.rows else 0)
            ),
        )

    async def health(self) -> SourceHealth:
        return SourceHealth(
            provider_id=self.provider_id,
            provider_version="test-v1",
            state=SourceHealthState.HEALTHY,
            checked_at=NOW,
        )


def request() -> CanonicalDatasetRequest:
    return CanonicalDatasetRequest(
        dataset_name="daily_market",
        as_of=NOW,
        start_date=date(2026, 7, 28),
        end_date=date(2026, 7, 28),
        fields=("instrument_id", "trade_date", "close"),
    )


def test_router_falls_back_as_a_whole_batch(tmp_path: Path) -> None:
    primary = FakeSource("miniqmt", ())
    fallback = FakeSource(
        "tushare",
        ({"instrument_id": "600519.SH", "trade_date": "20260728", "close": 1400.0},),
    )
    router = DatasetSourceRouter(
        adapters={"miniqmt": primary, "tushare": fallback},
        routes=(
            DatasetSourceRoute(
                dataset_name="daily_market",
                providers=("miniqmt", "tushare"),
                adapter_version="route-v1",
                quality_gate_version="daily-v1",
                timeout_seconds=2,
                required_fields=("instrument_id", "trade_date", "close"),
                primary_key=("instrument_id", "trade_date"),
            ),
        ),
        raw_store=FilesystemRawRecordStore(tmp_path),
    )

    result = asyncio.run(router.fetch(request()))

    assert result.batch.provider_id == "tushare"
    assert result.evidence.attempted_providers == ("miniqmt", "tushare")
    assert result.evidence.fallback_count == 1
    assert primary.calls == fallback.calls == 1
    assert len(list(tmp_path.rglob("*.json.gz"))) == 2


def test_duplicate_primary_key_rejects_primary_and_uses_fallback(tmp_path: Path) -> None:
    duplicate = (
        {"instrument_id": "600519.SH", "trade_date": "20260728", "close": 1400.0},
        {"instrument_id": "600519.SH", "trade_date": "20260728", "close": 1401.0},
    )
    primary = FakeSource("miniqmt", duplicate)
    fallback = FakeSource("tushare", duplicate[:1])
    route = DatasetSourceRoute(
        dataset_name="daily_market",
        providers=("miniqmt", "tushare"),
        adapter_version="route-v1",
        quality_gate_version="daily-v1",
        timeout_seconds=2,
        required_fields=("instrument_id", "trade_date", "close"),
        primary_key=("instrument_id", "trade_date"),
    )
    router = DatasetSourceRouter(
        adapters={"miniqmt": primary, "tushare": fallback},
        routes=(route,),
        raw_store=FilesystemRawRecordStore(tmp_path),
    )

    result = asyncio.run(router.fetch(request()))

    assert result.batch.rows == duplicate[:1]
    assert result.evidence.selected_provider == "tushare"


def test_partial_primary_is_discarded_before_whole_batch_fallback(tmp_path: Path) -> None:
    rows = ({"instrument_id": "600519.SH", "trade_date": "20260728", "close": 1400.0},)
    primary = FakeSource("miniqmt", rows, completeness=0.5)
    fallback = FakeSource("tushare", rows)
    router = DatasetSourceRouter(
        adapters={"miniqmt": primary, "tushare": fallback},
        routes=(
            DatasetSourceRoute(
                dataset_name="daily_market",
                providers=("miniqmt", "tushare"),
                adapter_version="route-v1",
                quality_gate_version="daily-v1",
                timeout_seconds=2,
                primary_key=("instrument_id", "trade_date"),
            ),
        ),
        raw_store=FilesystemRawRecordStore(tmp_path),
    )

    result = asyncio.run(router.fetch(request()))

    assert result.batch.provider_id == "tushare"
    assert result.evidence.fallback_reason == "source_incomplete:0.500000"


def test_routed_legacy_facade_preserves_one_raw_calendar_record(tmp_path: Path) -> None:
    raw_store = FilesystemRawRecordStore(tmp_path)
    source = FakeSource(
        "tushare",
        (
            {
                "exchange": "SSE",
                "cal_date": "20260729",
                "is_open": 1,
                "pretrade_date": "20260728",
            },
        ),
    )
    router = DatasetSourceRouter(
        adapters={"tushare": source},
        routes=(
            DatasetSourceRoute(
                dataset_name="trade_calendar",
                providers=("tushare",),
                adapter_version="route-v1",
                quality_gate_version="calendar-v1",
                timeout_seconds=2,
            ),
        ),
        raw_store=raw_store,
    )
    state: dict[str, object] = {"calendar": None, "industries": {}}
    workspace = tmp_path / "daily-runs/test"

    is_open, calendar_path, _ = asyncio.run(
        collect_calendar(
            state=state,
            state_path=workspace / "requests.json",
            workspace=workspace,
            target_date=date(2026, 7, 29),
            provider=RoutedHistoricalProvider(router),
            encoder=DuckDBParquetEncoder(),
            raw_store=raw_store,
        )
    )

    assert is_open is True
    assert calendar_path.is_file()
    assert len(list((tmp_path / "raw").rglob("*.json.gz"))) == 1


def test_routed_legacy_facade_allows_empty_paused_security_slice(tmp_path: Path) -> None:
    raw_store = FilesystemRawRecordStore(tmp_path)
    source = FakeSource("tushare", ())
    router = DatasetSourceRouter(
        adapters={"tushare": source},
        routes=(
            DatasetSourceRoute(
                dataset_name="security_master",
                providers=("tushare",),
                adapter_version="route-v1",
                quality_gate_version="security-v1",
                timeout_seconds=2,
                allow_empty=False,
            ),
        ),
        raw_store=raw_store,
    )

    table = asyncio.run(
        RoutedHistoricalProvider(router).query(
            "stock_basic",
            params={"list_status": "P"},
            fields=("ts_code", "list_status"),
        )
    )

    assert table.rows == ()
    assert table.raw_record_persisted is True
    assert len(list((tmp_path / "raw").rglob("*.json.gz"))) == 1


def test_routed_legacy_facade_preserves_explicit_daily_universe(tmp_path: Path) -> None:
    raw_store = FilesystemRawRecordStore(tmp_path)
    source = FakeSource(
        "miniqmt",
        (
            {"instrument_id": "000001.SZ", "trade_date": "20260729"},
            {"instrument_id": "920065.BJ", "trade_date": "20260729"},
        ),
    )
    router = DatasetSourceRouter(
        adapters={"miniqmt": source},
        routes=(
            DatasetSourceRoute(
                dataset_name="daily_market",
                providers=("miniqmt",),
                adapter_version="route-v3",
                quality_gate_version="cutover-v1",
                timeout_seconds=2,
            ),
        ),
        raw_store=raw_store,
    )

    asyncio.run(
        RoutedHistoricalProvider(router).query(
            "daily",
            params={
                "trade_date": "20260729",
                "universe": ("000001.SZ", "920065.BJ"),
            },
            fields=("ts_code", "trade_date"),
        )
    )

    assert source.requests[-1].universe == ("000001.SZ", "920065.BJ")


def test_provider_epoch_routes_cutover_dates_to_the_declared_source(tmp_path: Path) -> None:
    miniqmt = FakeSource(
        "miniqmt",
        ({"instrument_id": "600519.SH", "trade_date": "20260729", "close": 1400.0},),
    )
    tushare = FakeSource(
        "tushare",
        ({"instrument_id": "600519.SH", "trade_date": "20260728", "close": 1390.0},),
    )
    router = DatasetSourceRouter(
        adapters={"miniqmt": miniqmt, "tushare": tushare},
        routes=(
            DatasetSourceRoute(
                dataset_name="daily_market",
                providers=("miniqmt", "tushare"),
                adapter_version="route-v3",
                quality_gate_version="cutover-v1",
                timeout_seconds=2,
                provider_lineage=(
                    SourceProviderEpoch(
                        provider="tushare",
                        effective_from=date.min,
                        effective_to=date(2026, 7, 28),
                    ),
                    SourceProviderEpoch(
                        provider="miniqmt",
                        effective_from=date(2026, 7, 29),
                    ),
                ),
            ),
        ),
        raw_store=FilesystemRawRecordStore(tmp_path),
    )

    before = asyncio.run(
        router.fetch(
            request().model_copy(
                update={
                    "start_date": date(2026, 7, 28),
                    "end_date": date(2026, 7, 28),
                }
            )
        )
    )
    after = asyncio.run(
        router.fetch(
            request().model_copy(
                update={
                    "start_date": date(2026, 7, 29),
                    "end_date": date(2026, 7, 29),
                }
            )
        )
    )

    assert before.batch.provider_id == "tushare"
    assert before.evidence.attempted_providers == ("tushare",)
    assert after.batch.provider_id == "miniqmt"
    assert after.evidence.attempted_providers == ("miniqmt",)
    assert miniqmt.calls == tushare.calls == 1


def test_provider_epoch_rejects_request_spanning_cutover(tmp_path: Path) -> None:
    source = FakeSource("miniqmt", ())
    router = DatasetSourceRouter(
        adapters={"miniqmt": source, "tushare": FakeSource("tushare", ())},
        routes=(
            DatasetSourceRoute(
                dataset_name="daily_market",
                providers=("miniqmt", "tushare"),
                adapter_version="route-v3",
                quality_gate_version="cutover-v1",
                timeout_seconds=2,
                provider_lineage=(
                    SourceProviderEpoch(
                        provider="tushare",
                        effective_from=date.min,
                        effective_to=date(2026, 7, 28),
                    ),
                    SourceProviderEpoch(
                        provider="miniqmt",
                        effective_from=date(2026, 7, 29),
                    ),
                ),
            ),
        ),
        raw_store=FilesystemRawRecordStore(tmp_path),
    )

    with pytest.raises(SourceRouteError, match="request_crosses_provider_cutover"):
        asyncio.run(
            router.fetch(
                request().model_copy(
                    update={
                        "start_date": date(2026, 7, 28),
                        "end_date": date(2026, 7, 29),
                    }
                )
            )
        )
