from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable, Mapping, Sequence
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Literal, TypedDict

import pytest

from astramind_mini.data.adapters import (
    DailyPipelineStore,
    DataControlLedger,
    DuckDBParquetEncoder,
    FilesystemDatasetStore,
    FilesystemRawRecordStore,
    FilesystemSnapshotStore,
)
from astramind_mini.data.application import DataSnapshotBuilder, build_dataset_manifest
from astramind_mini.data.application.daily_pipeline import (
    DailyIndustryPipeline,
    DailyPipelineInterrupted,
)
from astramind_mini.data.application.daily_pipeline_inputs import DailyDatasetExtensions
from astramind_mini.data.application.dataset_schemas import (
    INDUSTRY_INDEX_DAILY_COLUMNS,
    INDUSTRY_MEMBERSHIP_COLUMNS,
    INDUSTRY_TAXONOMY_COLUMNS,
    TRADE_CALENDAR_COLUMNS,
)
from astramind_mini.data.application.identity import content_hash
from astramind_mini.data.contracts import (
    IndustryIndexDailyObservation,
    IndustryMembershipObservation,
    IndustryTaxonomyObservation,
    TradeCalendarObservation,
)
from astramind_mini.data.ports import ProviderTable
from astramind_mini.market_regime.adapters import FilesystemRotationStore


class SyntheticDailyProvider:
    def __init__(
        self,
        target: date,
        names: dict[str, tuple[Literal["L1", "L2"], str]],
    ) -> None:
        self.target = target
        self.names = names
        self.calls = 0
        self.received_at = datetime.combine(target, time(18, 5), tzinfo=UTC)

    async def query(
        self,
        api_name: str,
        *,
        params: Mapping[str, object],
        fields: Sequence[str],
    ) -> ProviderTable:
        self.calls += 1
        rows: tuple[dict[str, object], ...]
        if api_name == "trade_cal":
            rows = (
                {
                    "exchange": "SSE",
                    "cal_date": f"{self.target:%Y%m%d}",
                    "is_open": "1",
                    "pretrade_date": f"{self.target - timedelta(days=1):%Y%m%d}",
                },
            )
        else:
            assert api_name == "sw_daily"
            code = str(cast_dict(params)["ts_code"])
            index = sorted(self.names).index(code)
            close = 100 + index + 1.0
            rows = (
                {
                    "ts_code": code,
                    "trade_date": f"{self.target:%Y%m%d}",
                    "name": self.names[code][1],
                    "open": close - 0.2,
                    "low": close - 0.4,
                    "high": close + 0.4,
                    "close": close,
                    "change": 0.2,
                    "pct_change": 0.2,
                    "vol": 1000,
                    "amount": 2000,
                    "pe": 12,
                    "pb": 1.5,
                    "float_mv": 100,
                    "total_mv": 200,
                },
            )
        raw = {"code": 0, "data": rows}
        return ProviderTable(
            api_name=api_name,
            fields=tuple(str(item) for item in fields),
            rows=rows,
            raw_body=raw,
            request_identity=content_hash({"api": api_name, "params": params}),
            received_at=self.received_at,
            source_endpoint="https://example.invalid",
        )


def test_daily_pipeline_recovers_and_idempotently_commits_l1_l2(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "data"
    rotation_root = tmp_path / "rotation"
    control_db = tmp_path / "control.sqlite3"
    base_snapshot, target, names = _base_snapshot(data_root)
    provider = SyntheticDailyProvider(target, names)
    service = _service(data_root, rotation_root, control_db, provider)
    started_at = datetime.combine(target, time(18, 10), tzinfo=UTC)

    with pytest.raises(DailyPipelineInterrupted):
        asyncio.run(
            service.run(
                base_snapshot_id=base_snapshot,
                target_date=target,
                started_at=started_at,
                interrupt_after_step="dataset",
                include_research_inputs=False,
            )
        )
    store = DailyPipelineStore(control_db, data_root)
    interrupted = store.latest_status()
    assert interrupted is not None
    assert interrupted.state == "recovery_required"
    assert not (data_root / "current" / "daily-pipeline.json").exists()
    first_call_count = provider.calls

    publication = asyncio.run(
        service.run(
            base_snapshot_id=base_snapshot,
            target_date=target,
            started_at=started_at + timedelta(minutes=1),
            include_research_inputs=False,
        )
    )
    assert publication.status.state == "current"
    assert publication.status.observed_l1_count == 31
    assert publication.status.observed_l2_count == 1
    assert publication.commit is not None
    assert publication.commit.broker_actions_allowed is False
    assert provider.calls == first_call_count

    repeated = asyncio.run(
        service.run(
            base_snapshot_id=base_snapshot,
            target_date=target,
            started_at=started_at + timedelta(minutes=2),
            include_research_inputs=False,
        )
    )
    assert repeated.commit == publication.commit
    assert repeated.status.data_snapshot_id == publication.status.data_snapshot_id
    assert provider.calls == first_call_count
    assert store.journal_mode() == "wal"


def test_daily_pipeline_atomically_includes_dataset_extensions(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    rotation_root = tmp_path / "rotation"
    control_db = tmp_path / "control.sqlite3"
    base_snapshot, target, names = _base_snapshot(data_root)
    payload = b"etf-daily-extension"
    manifest = build_dataset_manifest(
        dataset_name="etf_daily",
        schema_version="test-v1",
        provider="fixture",
        source_endpoint="fixture",
        request_identity=content_hash("etf-extension"),
        retrieved_at=datetime.combine(target, time(18, 10), tzinfo=UTC),
        market_timezone="Asia/Shanghai",
        date_range=(target, target),
        universe=("159825.SZ",),
        primary_key=("instrument_id", "trade_date"),
        availability_rule="trade_date 18:00 Asia/Shanghai",
        units=("price:CNY",),
        row_count=1,
        artifacts={"etf_daily.parquet": payload},
    )
    extension_path = FilesystemDatasetStore(data_root).publish(
        manifest,
        {"etf_daily.parquet": payload},
    )

    async def prepare_extensions(
        _base_snapshot_id: str,
        _target_date: date,
    ) -> DailyDatasetExtensions:
        return DailyDatasetExtensions(
            manifests={"etf_daily": manifest},
            paths={"etf_daily": extension_path},
            retrieved_at=manifest.retrieved_at,
            known_gaps=("etf_extension_evidence_gap",),
        )

    publication = asyncio.run(
        _service(
            data_root,
            rotation_root,
            control_db,
            SyntheticDailyProvider(target, names),
            prepare_extensions=prepare_extensions,
        ).run(
            base_snapshot_id=base_snapshot,
            target_date=target,
            started_at=datetime.combine(target, time(18, 15), tzinfo=UTC),
            include_research_inputs=False,
            include_event_inputs=False,
        )
    )

    assert publication.commit is not None
    snapshot = FilesystemSnapshotStore(data_root).get(publication.commit.data_snapshot_id)
    assert "etf_daily" in {item.dataset_name for item in snapshot.datasets}
    assert "etf_extension_evidence_gap" in snapshot.known_gaps
    current = json.loads((data_root / "current/etf_daily.json").read_text(encoding="utf-8"))
    assert current["dataset_version"] == manifest.dataset_version


def test_explicit_recovery_supersedes_checkpoints_with_audit_history(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "data"
    rotation_root = tmp_path / "rotation"
    control_db = tmp_path / "control.sqlite3"
    base_snapshot, target, names = _base_snapshot(data_root)
    service = _service(
        data_root,
        rotation_root,
        control_db,
        SyntheticDailyProvider(target, names),
    )
    started_at = datetime.combine(target, time(18, 10), tzinfo=UTC)

    with pytest.raises(DailyPipelineInterrupted):
        asyncio.run(
            service.run(
                base_snapshot_id=base_snapshot,
                target_date=target,
                started_at=started_at,
                interrupt_after_step="dataset",
                include_research_inputs=False,
            )
        )
    store = DailyPipelineStore(control_db, data_root)
    interrupted = store.latest_status()
    assert interrupted is not None
    assert store.checkpoint(interrupted.run_id, "provider_collect") is not None
    assert store.checkpoint(interrupted.run_id, "dataset") is not None

    recovered = asyncio.run(
        service.run(
            base_snapshot_id=base_snapshot,
            target_date=target,
            started_at=started_at + timedelta(minutes=1),
            recover=True,
            include_research_inputs=False,
        )
    )

    assert recovered.status.state == "current"
    assert {value.step_id for value in store.checkpoint_history(interrupted.run_id)} == {
        "provider_collect",
        "dataset",
    }


def _service(
    data_root: Path,
    rotation_root: Path,
    control_db: Path,
    provider: SyntheticDailyProvider,
    prepare_extensions: (Callable[[str, date], Awaitable[DailyDatasetExtensions]] | None) = None,
) -> DailyIndustryPipeline:
    ledger = DataControlLedger(control_db)
    ledger.migrate()
    return DailyIndustryPipeline(
        data_root=data_root,
        rotation_root=rotation_root,
        provider=provider,
        encoder=DuckDBParquetEncoder(),
        raw_store=FilesystemRawRecordStore(data_root),
        dataset_store=FilesystemDatasetStore(data_root),
        snapshot_store=FilesystemSnapshotStore(data_root),
        rotation_store=FilesystemRotationStore(rotation_root),
        control_store=DailyPipelineStore(control_db, data_root),
        ledger=ledger,
        prepare_extensions=prepare_extensions,
    )


def _base_snapshot(
    root: Path,
) -> tuple[str, date, dict[str, tuple[Literal["L1", "L2"], str]]]:
    encoder = DuckDBParquetEncoder()
    start = date(2025, 1, 1)
    dates = tuple(start + timedelta(days=index) for index in range(142))
    target = dates[-1]
    observed = datetime.combine(dates[-2], time(18, 5), tzinfo=UTC)
    source = _source(observed)
    taxonomy, names = _taxonomy_fixture(source)
    memberships = tuple(
        IndustryMembershipObservation(
            **_source(datetime.combine(dates[0], time(18), tzinfo=UTC)),
            taxonomy="SW",
            taxonomy_version="SW2021",
            level="L1",
            industry_code=item.industry_code,
            industry_name=item.industry_name,
            instrument_id=f"{index:06d}.SZ",
            instrument_name=f"合成证券{index}",
            effective_from=dates[0],
            effective_to=None,
            is_current=True,
        )
        for item in taxonomy
        if item.level == "L1"
        for index in range(3)
    )
    daily = tuple(
        IndustryIndexDailyObservation(
            **_source(datetime.combine(day, time(18, 5), tzinfo=UTC)),
            taxonomy="SW",
            taxonomy_version="SW2021",
            level=level,
            industry_code=code,
            industry_name=name,
            trade_date=day,
            open=close - 0.2,
            high=close + 0.4,
            low=close - 0.4,
            close=close,
            change=0.1,
            percent_change=0.1,
            volume_provider_native=1000,
            amount_provider_native=2000,
            price_earnings=12,
            price_book=1.5,
            float_market_value_provider_native=100,
            total_market_value_provider_native=200,
        )
        for code_index, (code, (level, name)) in enumerate(sorted(names.items()))
        for day_index, day in enumerate(dates[:-1])
        for close in (100 + code_index + day_index * (0.01 + code_index * 0.0002),)
    )
    calendar = tuple(
        TradeCalendarObservation(
            **_source(datetime.combine(day, time(18, 5), tzinfo=UTC)),
            exchange="SSE",
            calendar_date=day,
            is_open=True,
            previous_trade_date=dates[index - 1] if index else None,
        )
        for index, day in enumerate(dates)
    )
    artifacts = {
        "trade_calendar": (
            encoder.encode(calendar, TRADE_CALENDAR_COLUMNS),
            ("exchange", "calendar_date"),
            (dates[0], dates[-1]),
        ),
        "industry_taxonomy": (
            encoder.encode(taxonomy, INDUSTRY_TAXONOMY_COLUMNS),
            ("industry_code",),
            (dates[-2], dates[-2]),
        ),
        "industry_membership": (
            encoder.encode(memberships, INDUSTRY_MEMBERSHIP_COLUMNS),
            ("level", "industry_code", "instrument_id", "effective_from"),
            (dates[0], dates[-2]),
        ),
        "industry_index_daily": (
            encoder.encode(daily, INDUSTRY_INDEX_DAILY_COLUMNS),
            ("level", "industry_code", "trade_date"),
            (dates[0], dates[-2]),
        ),
    }
    store = FilesystemDatasetStore(root)
    manifests = []
    for name, (payload, primary_key, date_range) in artifacts.items():
        manifest = build_dataset_manifest(
            dataset_name=name,
            schema_version="1.0.0",
            provider="synthetic",
            source_endpoint="fixture",
            request_identity=content_hash({"dataset": name}),
            retrieved_at=observed,
            market_timezone="Asia/Shanghai",
            date_range=date_range,
            universe=(),
            primary_key=primary_key,
            availability_rule="fixture",
            units=(),
            row_count={
                "trade_calendar": len(calendar),
                "industry_taxonomy": len(taxonomy),
                "industry_membership": len(memberships),
                "industry_index_daily": len(daily),
            }[name],
            artifacts={f"{name}.parquet": payload},
        )
        store.publish(manifest, {f"{name}.parquet": payload})
        manifests.append(manifest)
    snapshot = DataSnapshotBuilder().build(
        manifests=manifests,
        as_of=observed,
        created_at=observed,
        code_identity="synthetic-daily-pipeline-fixture-v1",
    )
    FilesystemSnapshotStore(root).publish(snapshot)
    return snapshot.snapshot_id, target, names


def _taxonomy_fixture(
    source: SourceFields,
) -> tuple[
    list[IndustryTaxonomyObservation],
    dict[str, tuple[Literal["L1", "L2"], str]],
]:
    taxonomy: list[IndustryTaxonomyObservation] = []
    names: dict[str, tuple[Literal["L1", "L2"], str]] = {}
    for index in range(31):
        code = f"80{index:04d}.SI"
        name = f"合成一级行业{index:02d}"
        names[code] = ("L1", name)
        taxonomy.append(
            IndustryTaxonomyObservation(
                **source,
                taxonomy="SW",
                taxonomy_version="SW2021",
                level="L1",
                industry_code=code,
                industry_name=name,
                provider_industry_code=f"{index:06d}",
                is_published=True,
                parent_code=None,
            )
        )
    l2_code = "899999.SI"
    names[l2_code] = ("L2", "合成二级行业")
    taxonomy.append(
        IndustryTaxonomyObservation(
            **source,
            taxonomy="SW",
            taxonomy_version="SW2021",
            level="L2",
            industry_code=l2_code,
            industry_name="合成二级行业",
            provider_industry_code="999999",
            is_published=True,
            parent_code=taxonomy[0].industry_code,
        )
    )
    return taxonomy, names


class SourceFields(TypedDict):
    provider: str
    source_endpoint: str
    retrieved_at: datetime
    available_at: datetime
    schema_version: str
    source_record_hash: str


def _source(at: datetime) -> SourceFields:
    return {
        "provider": "synthetic",
        "source_endpoint": "fixture",
        "retrieved_at": at,
        "available_at": at,
        "schema_version": "1.0.0",
        "source_record_hash": content_hash({"at": at}),
    }


def cast_dict(value: object) -> dict[str, object]:
    assert isinstance(value, dict)
    return value
