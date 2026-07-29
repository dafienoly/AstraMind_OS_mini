import asyncio
import json
from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime, timedelta
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
from astramind_mini.data.application.snapshot_reconciliation import (
    SnapshotDatasetReconciler,
)
from astramind_mini.data.contracts import DatasetManifest
from astramind_mini.data.etf_foundation.registry import ETF_CODES
from astramind_mini.data.etf_foundation.service import EtfFoundationService
from astramind_mini.data.ports import ProviderTable

RECEIVED_AT = datetime(2026, 7, 29, 10, tzinfo=UTC)
END_DATE = date(2026, 7, 29)


class SyntheticEtfProvider:
    async def query(
        self,
        api_name: str,
        *,
        params: Mapping[str, object],
        fields: Sequence[str],
    ) -> ProviderTable:
        rows = self._rows(api_name, params)
        raw_body = {
            "code": 0,
            "data": {"fields": list(fields), "items": rows},
        }
        return ProviderTable(
            api_name=api_name,
            fields=tuple(fields),
            rows=rows,
            raw_body=raw_body,
            request_identity=content_hash(
                {"api_name": api_name, "params": dict(params), "fields": fields}
            ),
            received_at=RECEIVED_AT,
            source_endpoint=f"synthetic.{api_name}",
            provider_id="synthetic-tushare",
            provider_version="fixture-v1",
        )

    def _rows(
        self,
        api_name: str,
        params: Mapping[str, object],
    ) -> tuple[dict[str, object], ...]:
        if api_name == "fund_basic":
            return tuple(
                {
                    "ts_code": code,
                    "name": f"合成ETF-{code}",
                    "fund_type": "股票型",
                    "invest_type": "被动指数型",
                    "benchmark": "合成基准",
                    "found_date": "20191201",
                    "list_date": "20200102",
                    "delist_date": "",
                    "status": "L",
                    "market": "E",
                }
                for code in ETF_CODES
            )
        code = str(params["ts_code"])
        if api_name == "fund_daily":
            return tuple(
                {
                    "ts_code": code,
                    "trade_date": f"{day:%Y%m%d}",
                    "open": 2.0,
                    "high": 2.1,
                    "low": 1.9,
                    "close": 2.0,
                    "pre_close": 2.0,
                    "change": 0.0,
                    "pct_chg": 0.0,
                    "vol": 1_000_000,
                    "amount": 50_000,
                }
                for day in (END_DATE - timedelta(days=252 - index) for index in range(253))
            )
        if api_name == "fund_share":
            return (
                {
                    "ts_code": code,
                    "trade_date": f"{END_DATE:%Y%m%d}",
                    "fd_share": 10_000,
                },
            )
        raise AssertionError(api_name)


def test_etf_foundation_publishes_four_immutable_datasets_and_snapshot(
    tmp_path: Path,
) -> None:
    base_snapshot_id = _publish_base_snapshot(tmp_path)
    ledger = DataControlLedger(tmp_path / "control/data.db")
    ledger.migrate()
    service = EtfFoundationService(
        data_root=tmp_path,
        provider=SyntheticEtfProvider(),
        raw_store=FilesystemRawRecordStore(tmp_path),
        encoder=DuckDBParquetEncoder(),
        dataset_store=FilesystemDatasetStore(tmp_path),
        snapshot_store=FilesystemSnapshotStore(tmp_path),
        ledger=ledger,
    )

    publication = asyncio.run(
        service.run(
            base_snapshot_id=base_snapshot_id,
            start_date=date(2025, 1, 1),
            end_date=END_DATE,
            activate=True,
        )
    )

    assert publication.activated is True
    assert publication.row_counts == {
        "etf_master": len(ETF_CODES),
        "etf_daily": len(ETF_CODES) * 253,
        "etf_share": len(ETF_CODES),
        "etf_industry_mapping": 32,
    }
    assert {item.dataset_name for item in publication.manifests} == {
        "etf_master",
        "etf_daily",
        "etf_share",
        "etf_industry_mapping",
    }
    assert len(publication.snapshot.datasets) == 5
    assert "etf_spread_not_in_foundation" in publication.snapshot.known_gaps
    assert "etf_daily_latest_before_requested_cutoff" not in publication.snapshot.known_gaps
    assert (
        "etf_share_historical_availability_uses_retrieval_time" in publication.snapshot.known_gaps
    )

    pointer = json.loads((tmp_path / "current/data-snapshot.json").read_text(encoding="utf-8"))
    assert pointer["snapshot_id"] == publication.snapshot.snapshot_id
    assert len(tuple((tmp_path / "raw/synthetic-tushare").rglob("*.json.gz"))) == (
        1 + 2 * len(ETF_CODES)
    )

    daily_manifest = next(
        item for item in publication.manifests if item.dataset_name == "etf_daily"
    )
    rows = DuckDBSnapshotQuery(tmp_path).query_parquet(
        daily_manifest,
        "etf_daily.parquet",
        "SELECT amount_cny, available_at FROM {dataset} ORDER BY instrument_id, trade_date LIMIT 1",
    )
    assert rows[0][0] == 50_000_000
    assert rows[0][1].hour == 18

    snapshot_store = FilesystemSnapshotStore(tmp_path)
    base = snapshot_store.get(base_snapshot_id)
    base_reference = base.datasets[0]
    base_manifest_path = (
        tmp_path
        / "datasets"
        / base_reference.dataset_name
        / base_reference.dataset_version.removeprefix("sha256:")
        / "manifest.json"
    )
    base_manifest = DatasetManifest.model_validate_json(
        base_manifest_path.read_text(encoding="utf-8")
    )
    advanced = DataSnapshotBuilder().build(
        manifests=(base_manifest,),
        as_of=RECEIVED_AT + timedelta(hours=1),
        created_at=RECEIVED_AT + timedelta(hours=1),
        code_identity="synthetic-daily-without-etf",
    )
    advanced_path = snapshot_store.publish(advanced)
    snapshot_store.activate(
        advanced,
        advanced_path,
        expected_snapshot_id=publication.snapshot.snapshot_id,
    )
    restored = SnapshotDatasetReconciler(
        data_root=tmp_path,
        datasets=FilesystemDatasetStore(tmp_path),
        snapshots=snapshot_store,
        ledger=ledger,
    ).restore(
        base_snapshot_id=advanced.snapshot_id,
        donor_snapshot_id=publication.snapshot.snapshot_id,
        dataset_names=(
            "etf_daily",
            "etf_industry_mapping",
            "etf_master",
            "etf_share",
        ),
        created_at=RECEIVED_AT + timedelta(hours=2),
        code_identity="synthetic-etf-reconciliation",
        donor_gap_prefixes=("etf_",),
    )

    assert len(restored.snapshot.datasets) == 5
    assert restored.restored_datasets == (
        "etf_daily",
        "etf_industry_mapping",
        "etf_master",
        "etf_share",
    )


def _publish_base_snapshot(root: Path) -> str:
    path = root / "base-source.parquet"
    output = str(path).replace("'", "''")
    with duckdb.connect(":memory:") as connection:
        connection.execute(
            f"COPY (SELECT ?::DATE AS calendar_date) TO '{output}' (FORMAT PARQUET)",
            [END_DATE],
        )
    artifacts = {"base.parquet": path.read_bytes()}
    manifest = build_dataset_manifest(
        dataset_name="trade_calendar",
        schema_version="test-v1",
        provider="fixture",
        source_endpoint="fixture",
        request_identity=content_hash("base-request"),
        retrieved_at=RECEIVED_AT,
        market_timezone="Asia/Shanghai",
        date_range=(END_DATE, END_DATE),
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
        as_of=RECEIVED_AT,
        created_at=RECEIVED_AT,
        code_identity="fixture",
        known_gaps=("etf_daily_latest_before_requested_cutoff",),
    )
    FilesystemSnapshotStore(root).publish(snapshot)
    return snapshot.snapshot_id
