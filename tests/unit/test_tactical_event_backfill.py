"""Focused proof for point-in-time tactical event publication."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime
from pathlib import Path

from astramind_mini.contracts import DataSnapshot
from astramind_mini.data.adapters import (
    DuckDBEventDatasetCompactor,
    DuckDBParquetEncoder,
    FilesystemDatasetStore,
    FilesystemRawRecordStore,
    FilesystemSnapshotStore,
)
from astramind_mini.data.application import DataSnapshotBuilder, TacticalEventBackfillService
from astramind_mini.data.application.daily_event_inputs import prepare_daily_event_inputs
from astramind_mini.data.application.dataset_schemas import TRADE_CALENDAR_COLUMNS
from astramind_mini.data.application.datasets import build_dataset_manifest
from astramind_mini.data.application.event_normalization import (
    normalize_lhb_events,
    normalize_shareholder_counts,
)
from astramind_mini.data.application.event_publication import build_event_manifests
from astramind_mini.data.application.identity import content_hash
from astramind_mini.data.contracts import TradeCalendarObservation
from astramind_mini.data.ports import ProviderTable

NOW = datetime(2026, 7, 27, tzinfo=UTC)


class _Provider:
    def __init__(self) -> None:
        self.queries: list[tuple[str, Mapping[str, object]]] = []

    async def query(
        self,
        api_name: str,
        *,
        params: Mapping[str, object],
        fields: Sequence[str],
    ) -> ProviderTable:
        del fields
        self.queries.append((api_name, params))
        key = str(params)
        event_date = next(
            (candidate for candidate in ("20220104", "20240104") if candidate in key),
            "20230103",
        )
        range_start = str(params.get("start_date", ""))
        range_end = str(params.get("end_date", ""))
        has_event = event_date in key or (
            bool(range_start) and range_start <= event_date <= range_end
        )
        holder_year = "2022" if "2022" in key else "2024" if "2024" in key else "2023"
        rows = {
            "top_list": (
                {
                    "trade_date": event_date,
                    "ts_code": "SYNTHETIC.SZ",
                    "name": "合成证券",
                    "close": 10.0,
                    "pct_change": 5.0,
                    "turnover_rate": 3.0,
                    "amount": 1000.0,
                    "l_sell": 100.0,
                    "l_buy": 200.0,
                    "l_amount": 300.0,
                    "net_amount": 100.0,
                    "net_rate": 10.0,
                    "amount_rate": 30.0,
                    "float_values": 5000.0,
                    "reason": "合成上榜原因",
                },
            )
            if has_event
            else (),
            "top_inst": (
                {
                    "trade_date": event_date,
                    "ts_code": "SYNTHETIC.SZ",
                    "exalter": "合成席位",
                    "side": "0",
                    "buy": 100.0,
                    "buy_rate": 10.0,
                    "sell": 50.0,
                    "sell_rate": 5.0,
                    "net_buy": 50.0,
                    "reason": "合成上榜原因",
                },
            )
            if has_event
            else (),
            "stk_holdernumber": (
                {
                    "ts_code": "SYNTHETIC.SZ",
                    "ann_date": f"{holder_year}0105",
                    "end_date": f"{int(holder_year) - 1}1231",
                    "holder_num": 1000,
                },
            ),
        }[api_name]
        body = {"code": 0, "data": {"fields": list(rows[0]) if rows else [], "items": []}}
        return ProviderTable(
            api_name=api_name,
            fields=tuple(rows[0]) if rows else (),
            rows=rows,
            raw_body=body,
            request_identity=content_hash({"api": api_name, "key": key}),
            received_at=NOW,
            source_endpoint="https://example.invalid",
        )


class _Ledger:
    def record_dataset(self, manifest: object, manifest_path: Path) -> None:
        del manifest, manifest_path

    def record_snapshot(self, snapshot: DataSnapshot, manifest_path: Path) -> None:
        del snapshot, manifest_path


def _base_snapshot(root: Path) -> str:
    rows = tuple(
        TradeCalendarObservation(
            provider="synthetic",
            source_endpoint="fixture",
            retrieved_at=NOW,
            available_at=NOW,
            schema_version="1",
            source_record_hash=content_hash({"date": value}),
            exchange="SSE",
            calendar_date=value,
            is_open=True,
        )
        for value in (
            date(2022, 1, 4),
            date(2022, 12, 30),
            date(2023, 1, 3),
            date(2023, 1, 4),
        )
    )
    artifacts = {
        "data.parquet": DuckDBParquetEncoder().encode(rows, TRADE_CALENDAR_COLUMNS),
    }
    manifest = build_dataset_manifest(
        dataset_name="trade_calendar",
        schema_version="1.0.0",
        provider="synthetic",
        source_endpoint="fixture",
        request_identity=content_hash("calendar"),
        retrieved_at=NOW,
        market_timezone="Asia/Shanghai",
        date_range=(date(2022, 1, 4), date(2023, 1, 4)),
        universe=("SSE",),
        primary_key=("exchange", "calendar_date"),
        availability_rule="fixture",
        units=(),
        row_count=4,
        artifacts=artifacts,
    )
    dataset_store = FilesystemDatasetStore(root)
    dataset_store.publish(manifest, artifacts)
    snapshot = DataSnapshotBuilder().build(
        manifests=(manifest,),
        as_of=NOW,
        created_at=NOW,
        code_identity="fixture",
    )
    FilesystemSnapshotStore(root).publish(snapshot)
    return snapshot.snapshot_id


def test_event_backfill_is_resumable_and_publishes_point_in_time_data(
    tmp_path: Path,
) -> None:
    root = tmp_path / "data"
    snapshot_id = _base_snapshot(root)
    provider = _Provider()
    service = TacticalEventBackfillService(
        data_root=root,
        provider=provider,
        raw_store=FilesystemRawRecordStore(root),
        encoder=DuckDBParquetEncoder(),
        compactor=DuckDBEventDatasetCompactor(),
        dataset_store=FilesystemDatasetStore(root),
        snapshot_store=FilesystemSnapshotStore(root),
        ledger=_Ledger(),
    )
    first = asyncio.run(
        service.run(
            base_snapshot_id=snapshot_id,
            start_date=date(2023, 1, 1),
            end_date=date(2023, 1, 31),
        )
    )
    repeated = asyncio.run(
        service.run(
            base_snapshot_id=snapshot_id,
            start_date=date(2023, 1, 1),
            end_date=date(2023, 1, 31),
        )
    )
    assert first.snapshot.snapshot_id == repeated.snapshot.snapshot_id
    assert first.request_count == 9
    assert all(
        set(params) == {"trade_date"}
        for api_name, params in provider.queries
        if api_name == "top_list"
    )
    assert {item.dataset_name: item.row_count for item in first.manifests} == {
        "lhb_event": 1,
        "lhb_seat": 1,
        "shareholder_count": 1,
    }


def test_event_backfill_merges_an_earlier_window_with_current_events(
    tmp_path: Path,
) -> None:
    root = tmp_path / "data"
    snapshot_id = _base_snapshot(root)
    service = TacticalEventBackfillService(
        data_root=root,
        provider=_Provider(),
        raw_store=FilesystemRawRecordStore(root),
        encoder=DuckDBParquetEncoder(),
        compactor=DuckDBEventDatasetCompactor(),
        dataset_store=FilesystemDatasetStore(root),
        snapshot_store=FilesystemSnapshotStore(root),
        ledger=_Ledger(),
    )
    asyncio.run(
        service.run(
            base_snapshot_id=snapshot_id,
            start_date=date(2023, 1, 1),
            end_date=date(2023, 1, 31),
        )
    )
    merged = asyncio.run(
        service.run(
            base_snapshot_id=snapshot_id,
            start_date=date(2022, 1, 1),
            end_date=date(2022, 1, 31),
        )
    )
    assert {item.dataset_name: item.row_count for item in merged.manifests} == {
        "lhb_event": 2,
        "lhb_seat": 2,
        "shareholder_count": 2,
    }
    assert all(
        item.date_range == (date(2022, 1, 1), date(2023, 1, 31)) for item in merged.manifests
    )


def test_shareholder_windows_never_cross_year_boundaries(tmp_path: Path) -> None:
    root = tmp_path / "data"
    snapshot_id = _base_snapshot(root)
    provider = _Provider()
    service = TacticalEventBackfillService(
        data_root=root,
        provider=provider,
        raw_store=FilesystemRawRecordStore(root),
        encoder=DuckDBParquetEncoder(),
        compactor=DuckDBEventDatasetCompactor(),
        dataset_store=FilesystemDatasetStore(root),
        snapshot_store=FilesystemSnapshotStore(root),
        ledger=_Ledger(),
    )
    asyncio.run(
        service.run(
            base_snapshot_id=snapshot_id,
            start_date=date(2022, 12, 25),
            end_date=date(2023, 1, 8),
        )
    )
    holder_ranges = [
        (str(params["start_date"]), str(params["end_date"]))
        for api_name, params in provider.queries
        if api_name == "stk_holdernumber"
    ]
    assert holder_ranges == [
        ("20221225", "20221231"),
        ("20230101", "20230107"),
        ("20230108", "20230108"),
    ]


def test_event_manifest_discloses_provider_empty_early_years(tmp_path: Path) -> None:
    annual: dict[str, dict[int, dict[str, object]]] = {}
    for name in ("lhb_event", "lhb_seat", "shareholder_count"):
        path = tmp_path / f"{name}-2012.parquet"
        path.write_bytes(b"synthetic")
        annual[name] = {
            2012: {
                "path": str(path),
                "hash": content_hash(name),
                "rows": 1,
                "start_date": "2012-01-04",
                "end_date": "2012-01-04",
            }
        }
    manifests, _ = build_event_manifests(
        import_id=content_hash("event-import"),
        start_date=date(2005, 1, 1),
        end_date=date(2012, 12, 31),
        annual=annual,
        staging=tmp_path,
        retrieved_at=NOW,
    )
    assert all(
        "provider_empty_years_before_first_observation:2005-2011" in item.known_gaps
        for item in manifests
    )


def test_daily_event_increment_extends_current_event_versions(tmp_path: Path) -> None:
    root = tmp_path / "data"
    snapshot_id = _base_snapshot(root)
    service = TacticalEventBackfillService(
        data_root=root,
        provider=_Provider(),
        raw_store=FilesystemRawRecordStore(root),
        encoder=DuckDBParquetEncoder(),
        compactor=DuckDBEventDatasetCompactor(),
        dataset_store=FilesystemDatasetStore(root),
        snapshot_store=FilesystemSnapshotStore(root),
        ledger=_Ledger(),
    )
    first = asyncio.run(
        service.run(
            base_snapshot_id=snapshot_id,
            start_date=date(2023, 1, 1),
            end_date=date(2023, 1, 31),
        )
    )
    state: dict[str, object] = {"events": {}}
    daily = asyncio.run(
        prepare_daily_event_inputs(
            root=root,
            provider=_Provider(),
            raw_store=FilesystemRawRecordStore(root),
            encoder=DuckDBParquetEncoder(),
            snapshot_manifests={item.dataset_name: item for item in first.manifests},
            workspace=tmp_path / "daily",
            state=state,
            state_path=tmp_path / "daily" / "state.json",
            target_date=date(2024, 1, 4),
        )
    )
    assert daily is not None
    assert {name: item.row_count for name, item in daily.manifests.items()} == {
        "lhb_event": 2,
        "lhb_seat": 2,
        "shareholder_count": 2,
    }
    assert all(
        item.date_range == (date(2023, 1, 1), date(2024, 1, 4)) for item in daily.manifests.values()
    )


def test_event_availability_uses_market_close_and_announcement_date() -> None:
    lhb_table = _table(
        "top_list",
        {
            "trade_date": "20230103",
            "ts_code": "SYNTHETIC.SZ",
            "name": "合成证券",
            "close": 10,
            "pct_change": 5,
            "turnover_rate": 3,
            "amount": 1000,
            "l_sell": 100,
            "l_buy": 200,
            "l_amount": 300,
            "net_amount": 100,
            "net_rate": 10,
            "amount_rate": 30,
            "float_values": 5000,
            "reason": "合成原因",
        },
    )
    holder_table = _table(
        "stk_holdernumber",
        {
            "ts_code": "SYNTHETIC.SZ",
            "ann_date": "20230201",
            "end_date": "20221231",
            "holder_num": 1000,
        },
    )
    event = normalize_lhb_events(lhb_table)[0]
    holder = normalize_shareholder_counts(holder_table)[0]
    assert event.available_at.isoformat() == "2023-01-03T18:00:00+08:00"
    assert holder.available_at.isoformat() == "2023-02-01T18:00:00+08:00"
    assert holder.reporting_period < holder.announced_on


def test_unknown_holder_count_is_explicit_and_not_zero_filled() -> None:
    holder = normalize_shareholder_counts(
        _table(
            "stk_holdernumber",
            {
                "ts_code": "SYNTHETIC.SZ",
                "ann_date": "20230201",
                "end_date": "20221231",
                "holder_num": None,
            },
        )
    )[0]
    assert holder.holder_count is None


def test_holder_period_after_announcement_is_not_available_early() -> None:
    holder = normalize_shareholder_counts(
        _table(
            "stk_holdernumber",
            {
                "ts_code": "SYNTHETIC.SZ",
                "ann_date": "20230101",
                "end_date": "20230131",
                "holder_num": 1000,
            },
        )
    )[0]
    assert holder.announced_on < holder.reporting_period
    assert holder.available_at.isoformat() == "2023-01-31T18:00:00+08:00"


def _table(api_name: str, row: dict[str, object]) -> ProviderTable:
    return ProviderTable(
        api_name=api_name,
        fields=tuple(row),
        rows=(row,),
        raw_body={"code": 0},
        request_identity=content_hash({"api": api_name}),
        received_at=NOW,
        source_endpoint="fixture",
    )
