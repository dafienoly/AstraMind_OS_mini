"""Publish official ETF model evidence into an immutable DataSnapshot."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from pydantic import BaseModel

from astramind_mini.contracts import DataSnapshot
from astramind_mini.data.application.datasets import (
    DataSnapshotBuilder,
    build_dataset_manifest,
)
from astramind_mini.data.application.identity import content_hash
from astramind_mini.data.contracts import DatasetManifest
from astramind_mini.data.etf_foundation.registry import ETF_CODES
from astramind_mini.data.ports import (
    DataArtifactLedger,
    FileDatasetStore,
    ParquetEncoder,
    ReleasableSnapshotStore,
)

from .collection import EtfOfficialEvidenceCollection, EtfOfficialEvidenceCollector
from .schemas import (
    ETF_NAV_COLUMNS,
    ETF_OFFICIAL_BENCHMARK_COLUMNS,
    OFFICIAL_INDEX_DAILY_COLUMNS,
)


@dataclass(frozen=True, slots=True)
class EtfOfficialEvidencePublication:
    snapshot: DataSnapshot
    manifests: tuple[DatasetManifest, ...]
    row_counts: dict[str, int]
    activated: bool


class EtfOfficialEvidenceService:
    def __init__(
        self,
        *,
        data_root: Path,
        collector: EtfOfficialEvidenceCollector,
        encoder: ParquetEncoder,
        dataset_store: FileDatasetStore,
        snapshot_store: ReleasableSnapshotStore,
        ledger: DataArtifactLedger,
    ) -> None:
        self._root = data_root
        self._collector = collector
        self._encoder = encoder
        self._datasets = dataset_store
        self._snapshots = snapshot_store
        self._ledger = ledger

    async def run(
        self,
        *,
        base_snapshot_id: str,
        start_date: date,
        end_date: date,
        activate: bool = False,
    ) -> EtfOfficialEvidencePublication:
        collection = await self._collector.collect(
            start_date=start_date,
            end_date=end_date,
        )
        payloads = self._payloads(collection)
        request_identity = content_hash(
            {
                "base_snapshot_id": base_snapshot_id,
                "start_date": start_date,
                "end_date": end_date,
                "etf_codes": ETF_CODES,
                "official_benchmark_codes": sorted(
                    {row.benchmark_code for row in collection.benchmarks}
                ),
            }
        )
        manifests = self._manifests(collection, payloads, request_identity)
        manifest_paths = {}
        for manifest in manifests:
            artifact = f"{manifest.dataset_name}.parquet"
            path = self._datasets.publish(
                manifest,
                {artifact: payloads[manifest.dataset_name][1]},
            )
            self._ledger.record_dataset(manifest, path)
            manifest_paths[manifest.dataset_name] = path
        base = self._snapshots.get(base_snapshot_id)
        all_manifests = self._base_manifests(base)
        all_manifests.update({item.dataset_name: item for item in manifests})
        snapshot = DataSnapshotBuilder().build(
            manifests=tuple(all_manifests.values()),
            as_of=max(base.as_of, collection.retrieved_at),
            created_at=collection.retrieved_at,
            code_identity="wp-0054-etf-official-evidence-v1",
            known_gaps=(
                *base.known_gaps,
                "etf_official_mapping_historical_availability_unknown",
                "etf_l1_spread_60_session_window_pending",
            ),
        )
        snapshot_path = self._snapshots.publish(snapshot)
        self._ledger.record_snapshot(snapshot, snapshot_path)
        if activate:
            for manifest in manifests:
                self._datasets.activate(manifest, manifest_paths[manifest.dataset_name])
            self._snapshots.activate(
                snapshot,
                snapshot_path,
                expected_snapshot_id=base.snapshot_id,
            )
        return EtfOfficialEvidencePublication(
            snapshot=snapshot,
            manifests=manifests,
            row_counts={name: len(rows) for name, (rows, _) in payloads.items()},
            activated=activate,
        )

    def _payloads(
        self,
        collection: EtfOfficialEvidenceCollection,
    ) -> dict[str, tuple[tuple[BaseModel, ...], bytes]]:
        definitions = {
            "etf_official_benchmark": (
                collection.benchmarks,
                ETF_OFFICIAL_BENCHMARK_COLUMNS,
            ),
            "etf_nav": (collection.nav, ETF_NAV_COLUMNS),
            "official_index_daily": (
                collection.index_daily,
                OFFICIAL_INDEX_DAILY_COLUMNS,
            ),
        }
        return {
            name: (rows, self._encoder.encode(rows, columns))
            for name, (rows, columns) in definitions.items()
        }

    @staticmethod
    def _manifests(
        collection: EtfOfficialEvidenceCollection,
        payloads: dict[str, tuple[tuple[BaseModel, ...], bytes]],
        request_identity: str,
    ) -> tuple[DatasetManifest, ...]:
        definitions = (
            (
                "etf_official_benchmark",
                collection.benchmarks,
                ("instrument_id", "effective_from"),
                (
                    min(row.effective_from for row in collection.benchmarks),
                    max(row.effective_from for row in collection.benchmarks),
                ),
                ("benchmark_identity:provider_official",),
                "provider current registry available at retrieval time",
                ("historical_mapping_availability_unknown",),
            ),
            (
                "etf_nav",
                collection.nav,
                ("instrument_id", "nav_date"),
                (
                    min(row.nav_date for row in collection.nav),
                    max(row.nav_date for row in collection.nav),
                ),
                ("nav:CNY_per_share",),
                "ann_date 18:00 Asia/Shanghai",
                (),
            ),
            (
                "official_index_daily",
                collection.index_daily,
                ("index_code", "trade_date"),
                (
                    min(row.trade_date for row in collection.index_daily),
                    max(row.trade_date for row in collection.index_daily),
                ),
                ("price:index_points", "volume:provider_native", "amount:provider_native"),
                "trade_date 18:00 Asia/Shanghai",
                (
                    ("provider_ohlc_or_previous_close_missing",)
                    if any(
                        row.open is None
                        or row.high is None
                        or row.low is None
                        or row.previous_close is None
                        for row in collection.index_daily
                    )
                    else ()
                ),
            ),
        )
        return tuple(
            build_dataset_manifest(
                dataset_name=name,
                schema_version="1.0.0",
                provider=rows[0].provider,
                source_endpoint=rows[0].source_endpoint,
                request_identity=request_identity,
                retrieved_at=collection.retrieved_at,
                market_timezone="Asia/Shanghai",
                date_range=date_range,
                universe=sorted(
                    {getattr(row, "instrument_id", getattr(row, "index_code", "")) for row in rows}
                ),
                primary_key=primary_key,
                availability_rule=availability,
                units=units,
                row_count=len(rows),
                artifacts={f"{name}.parquet": payloads[name][1]},
                known_gaps=gaps,
            )
            for name, rows, primary_key, date_range, units, availability, gaps in definitions
        )

    def _base_manifests(self, snapshot: DataSnapshot) -> dict[str, DatasetManifest]:
        result = {}
        for reference in snapshot.datasets:
            digest = reference.dataset_version.removeprefix("sha256:")
            path = self._root / "datasets" / reference.dataset_name / digest / "manifest.json"
            manifest = DatasetManifest.model_validate_json(path.read_text(encoding="utf-8"))
            if manifest.content_hash != reference.content_hash:
                raise ValueError(f"基础数据集身份冲突：{reference.dataset_name}")
            result[reference.dataset_name] = manifest
        return result


__all__ = ["EtfOfficialEvidencePublication", "EtfOfficialEvidenceService"]
