from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime
from pathlib import Path

import duckdb

from astramind_mini.data.adapters import (
    DataControlLedger,
    DuckDBParquetEncoder,
    DuckDBSnapshotQuery,
    FilesystemDatasetStore,
    FilesystemRawRecordStore,
    FilesystemSnapshotStore,
)
from astramind_mini.data.application.datasets import (
    DataSnapshotBuilder,
    build_dataset_manifest,
)
from astramind_mini.data.application.identity import content_hash
from astramind_mini.data.etf_foundation.registry import ETF_CODES
from astramind_mini.data.etf_model_evidence import (
    EtfOfficialEvidenceCollector,
    EtfOfficialEvidenceService,
)
from astramind_mini.data.ports import ProviderTable

NOW = datetime(2026, 7, 29, 10, tzinfo=UTC)
DAY = date(2026, 7, 29)


class SyntheticOfficialProvider:
    async def query(
        self,
        api_name: str,
        *,
        params: Mapping[str, object],
        fields: Sequence[str],
    ) -> ProviderTable:
        rows = self._rows(api_name, params)
        return ProviderTable(
            api_name=api_name,
            fields=tuple(fields),
            rows=rows,
            raw_body={"code": 0, "data": {"fields": list(fields), "items": rows}},
            request_identity=content_hash((api_name, dict(params), tuple(fields))),
            received_at=NOW,
            source_endpoint=f"synthetic.{api_name}",
            provider_id="synthetic-tushare",
            provider_version="fixture-v1",
        )

    @staticmethod
    def _rows(
        api_name: str,
        params: Mapping[str, object],
    ) -> tuple[dict[str, object], ...]:
        if api_name == "etf_basic":
            return tuple(
                {
                    "ts_code": code,
                    "csname": code,
                    "index_code": "000001.CSI",
                    "index_name": "合成官方指数",
                    "list_status": "L",
                    "exchange": code[-2:],
                }
                for code in ETF_CODES
            )
        if api_name == "fund_nav":
            return (
                {
                    "ts_code": params["ts_code"],
                    "ann_date": "20260729",
                    "nav_date": "20260729",
                    "unit_nav": 1.0,
                    "accum_nav": 1.0,
                    "adj_nav": 1.0,
                },
            )
        if api_name == "index_daily":
            return (
                {
                    "ts_code": params["ts_code"],
                    "trade_date": "20260729",
                    "open": 100.0,
                    "high": 101.0,
                    "low": 99.0,
                    "close": 100.0,
                    "pre_close": 100.0,
                    "change": 0.0,
                    "pct_chg": 0.0,
                    "vol": 10.0,
                    "amount": 20.0,
                },
            )
        raise AssertionError(api_name)


def test_official_etf_evidence_publishes_three_datasets_without_claiming_history(
    tmp_path: Path,
) -> None:
    base_id = _base_snapshot(tmp_path)
    ledger = DataControlLedger(tmp_path / "control/data.db")
    ledger.migrate()
    publication = asyncio.run(
        EtfOfficialEvidenceService(
            data_root=tmp_path,
            collector=EtfOfficialEvidenceCollector(
                provider=SyntheticOfficialProvider(),
                raw_store=FilesystemRawRecordStore(tmp_path),
            ),
            encoder=DuckDBParquetEncoder(),
            dataset_store=FilesystemDatasetStore(tmp_path),
            snapshot_store=FilesystemSnapshotStore(tmp_path),
            ledger=ledger,
        ).run(
            base_snapshot_id=base_id,
            start_date=DAY,
            end_date=DAY,
            activate=True,
        )
    )
    assert publication.row_counts == {
        "etf_nav": len(ETF_CODES),
        "etf_official_benchmark": len(ETF_CODES),
        "official_index_daily": 2,
    }
    assert "etf_official_mapping_historical_availability_unknown" in (
        publication.snapshot.known_gaps
    )
    pointer = json.loads((tmp_path / "current/data-snapshot.json").read_text(encoding="utf-8"))
    assert pointer["snapshot_id"] == publication.snapshot.snapshot_id
    benchmark_manifest = next(
        item for item in publication.manifests if item.dataset_name == "etf_official_benchmark"
    )
    row = DuckDBSnapshotQuery(tmp_path).query_parquet(
        benchmark_manifest,
        "etf_official_benchmark.parquet",
        "SELECT historical_availability_known FROM {dataset} LIMIT 1",
    )
    assert row == [(False,)]


def _base_snapshot(root: Path) -> str:
    path = root / "base-source.parquet"
    output = str(path).replace("'", "''")
    with duckdb.connect(":memory:") as connection:
        connection.execute(
            f"COPY (SELECT ?::DATE AS calendar_date) TO '{output}' (FORMAT PARQUET)",
            [DAY],
        )
    artifacts = {"base.parquet": path.read_bytes()}
    manifest = build_dataset_manifest(
        dataset_name="trade_calendar",
        schema_version="test-v1",
        provider="fixture",
        source_endpoint="fixture",
        request_identity=content_hash("base"),
        retrieved_at=NOW,
        market_timezone="Asia/Shanghai",
        date_range=(DAY, DAY),
        universe=("SSE",),
        primary_key=("calendar_date",),
        availability_rule="fixture",
        units=(),
        row_count=1,
        artifacts=artifacts,
    )
    FilesystemDatasetStore(root).publish(manifest, artifacts)
    snapshot = DataSnapshotBuilder().build(
        manifests=(manifest,),
        as_of=NOW,
        created_at=NOW,
        code_identity="fixture",
    )
    path = FilesystemSnapshotStore(root).publish(snapshot)
    FilesystemSnapshotStore(root).activate(snapshot, path)
    return snapshot.snapshot_id
