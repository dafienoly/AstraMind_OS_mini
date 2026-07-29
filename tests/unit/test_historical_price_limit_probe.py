"""Focused proof for fail-closed pre-2007 price-limit coverage probing."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime
from pathlib import Path

from astramind_mini.data.adapters import (
    DuckDBParquetEncoder,
    FilesystemDatasetStore,
    FilesystemRawRecordStore,
    FilesystemSnapshotStore,
)
from astramind_mini.data.application import DataSnapshotBuilder
from astramind_mini.data.application.dataset_schemas import TRADE_CALENDAR_COLUMNS
from astramind_mini.data.application.datasets import build_dataset_manifest
from astramind_mini.data.application.historical_price_limit_probe import (
    HistoricalPriceLimitProbeService,
)
from astramind_mini.data.application.identity import content_hash
from astramind_mini.data.contracts import TradeCalendarObservation
from astramind_mini.data.ports import ProviderTable

NOW = datetime(2026, 7, 28, tzinfo=UTC)


class _Provider:
    async def query(
        self,
        api_name: str,
        *,
        params: Mapping[str, object],
        fields: Sequence[str],
    ) -> ProviderTable:
        del fields
        assert api_name == "stk_limit"
        trade_date = str(params["trade_date"])
        rows = (
            (
                {
                    "trade_date": trade_date,
                    "ts_code": "000001.SZ",
                    "pre_close": 10,
                    "up_limit": 11,
                    "down_limit": 9,
                },
            )
            if trade_date == "20000104"
            else ()
        )
        return ProviderTable(
            api_name=api_name,
            fields=tuple(rows[0]) if rows else (),
            rows=rows,
            raw_body={"code": 0, "trade_date": trade_date},
            request_identity=content_hash({"api": api_name, "trade_date": trade_date}),
            received_at=NOW,
            source_endpoint="fixture",
        )


def test_probe_does_not_publish_when_any_session_is_empty(tmp_path: Path) -> None:
    root = tmp_path / "data"
    snapshot_id = _base_snapshot(root)
    result = asyncio.run(
        HistoricalPriceLimitProbeService(
            data_root=root,
            provider=_Provider(),
            raw_store=FilesystemRawRecordStore(root),
            encoder=DuckDBParquetEncoder(),
        ).run(
            base_snapshot_id=snapshot_id,
            start_date=date(2000, 1, 4),
            end_date=date(2000, 1, 5),
        )
    )
    assert result.state == "historical_unavailable"
    assert result.expected_sessions == 2
    assert result.observed_sessions == 2
    assert result.empty_sessions == (date(2000, 1, 5),)
    assert result.artifact_path.is_file()
    assert not (root / "current" / "price_limit.json").exists()


def _base_snapshot(root: Path) -> str:
    days = (date(2000, 1, 4), date(2000, 1, 5))
    rows = tuple(
        TradeCalendarObservation(
            provider="synthetic",
            source_endpoint="fixture",
            retrieved_at=NOW,
            available_at=NOW,
            schema_version="1.0.0",
            source_record_hash=content_hash({"date": value}),
            exchange="SSE",
            calendar_date=value,
            is_open=True,
        )
        for value in days
    )
    artifacts = {
        "trade-calendar.parquet": DuckDBParquetEncoder().encode(rows, TRADE_CALENDAR_COLUMNS)
    }
    manifest = build_dataset_manifest(
        dataset_name="trade_calendar",
        schema_version="1.0.0",
        provider="synthetic",
        source_endpoint="fixture",
        request_identity=content_hash("calendar"),
        retrieved_at=NOW,
        market_timezone="Asia/Shanghai",
        date_range=(days[0], days[-1]),
        universe=("SSE",),
        primary_key=("exchange", "calendar_date"),
        availability_rule="fixture",
        units=(),
        row_count=len(rows),
        artifacts=artifacts,
    )
    FilesystemDatasetStore(root).publish(manifest, artifacts)
    snapshot = DataSnapshotBuilder().build(
        manifests=(manifest,),
        as_of=NOW,
        created_at=NOW,
        code_identity="fixture",
    )
    FilesystemSnapshotStore(root).publish(snapshot)
    return snapshot.snapshot_id
