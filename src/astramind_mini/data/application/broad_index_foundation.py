"""Bootstrap the versioned six-index daily dataset for WP-0038."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from astramind_mini.contracts import DataSnapshot

from ..contracts import BroadIndexDailyObservation, DatasetManifest, RawRecordEnvelope
from ..ports import (
    DataArtifactLedger,
    DatasetStore,
    HistoricalMarketDataProvider,
    ParquetEncoder,
    RawRecordStore,
    SnapshotStore,
)
from .broad_index_normalization import (
    BROAD_INDEX_REGISTRY,
    INDEX_DAILY_FIELDS,
    normalize_broad_index_daily,
)
from .dataset_schemas import BROAD_INDEX_DAILY_COLUMNS
from .datasets import DataSnapshotBuilder, build_dataset_manifest
from .identity import content_hash


@dataclass(frozen=True, slots=True)
class BroadIndexPublication:
    snapshot: DataSnapshot
    manifest: DatasetManifest
    row_count: int


class BroadIndexFoundationService:
    def __init__(
        self,
        *,
        data_root: Path,
        provider: HistoricalMarketDataProvider,
        raw_store: RawRecordStore,
        encoder: ParquetEncoder,
        dataset_store: DatasetStore,
        snapshot_store: SnapshotStore,
        ledger: DataArtifactLedger,
    ) -> None:
        self._root = data_root
        self._provider = provider
        self._raw = raw_store
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
    ) -> BroadIndexPublication:
        if start_date > end_date:
            raise ValueError("宽基指数开始日期不能晚于结束日期")
        observations: list[BroadIndexDailyObservation] = []
        retrieved_at = None
        for code in BROAD_INDEX_REGISTRY:
            for window_start, window_end in _windows(start_date, end_date):
                table = await self._provider.query(
                    "index_daily",
                    params={
                        "ts_code": code,
                        "start_date": window_start.strftime("%Y%m%d"),
                        "end_date": window_end.strftime("%Y%m%d"),
                    },
                    fields=INDEX_DAILY_FIELDS,
                )
                if len(table.rows) >= 6_000:
                    raise ValueError(f"index_daily 可能被提供方截断：{code}:{window_start}")
                self._preserve(table)
                observations.extend(normalize_broad_index_daily(table))
                retrieved_at = (
                    max(retrieved_at, table.received_at) if retrieved_at else table.received_at
                )
        if retrieved_at is None:
            raise ValueError("宽基指数提供方没有返回请求")
        unique = {(row.instrument_id, row.trade_date): row for row in observations}
        rows = tuple(unique[key] for key in sorted(unique))
        _validate_coverage(rows, end_date)
        sources = {(row.provider, row.source_endpoint) for row in rows}
        providers = {provider for provider, _ in sources}
        if len(providers) != 1:
            raise ValueError("宽基指数同一数据集版本不得混用提供方")
        payload = self._encoder.encode(rows, BROAD_INDEX_DAILY_COLUMNS)
        request_identity = content_hash(
            {
                "registry": "a-share-broad-index-v1",
                "start_date": start_date,
                "end_date": end_date,
                "codes": tuple(BROAD_INDEX_REGISTRY),
            }
        )
        manifest = build_dataset_manifest(
            dataset_name="broad_index_daily",
            schema_version="1.0.0",
            provider=rows[0].provider,
            source_endpoint=(
                next(iter(sources))[1] if len(sources) == 1 else "multiple-provider-endpoints"
            ),
            request_identity=request_identity,
            retrieved_at=retrieved_at,
            market_timezone="Asia/Shanghai",
            date_range=(min(row.trade_date for row in rows), max(row.trade_date for row in rows)),
            universe=tuple(BROAD_INDEX_REGISTRY),
            primary_key=("instrument_id", "trade_date"),
            availability_rule="trade_date 18:00 Asia/Shanghai",
            units=(
                "price:index_points",
                "volume:lots",
                "amount:CNY",
                "percent_change:percent",
            ),
            row_count=len(rows),
            artifacts={"broad_index_daily.parquet": payload},
        )
        manifest_path = self._datasets.publish(manifest, {"broad_index_daily.parquet": payload})
        self._ledger.record_dataset(manifest, manifest_path)
        base = self._snapshots.get(base_snapshot_id)
        manifests = self._base_manifests(base)
        manifests["broad_index_daily"] = manifest
        snapshot = DataSnapshotBuilder().build(
            manifests=tuple(manifests.values()),
            as_of=max(base.as_of, retrieved_at),
            created_at=retrieved_at,
            code_identity="wp-0038-broad-index-foundation-v1",
            known_gaps=base.known_gaps,
        )
        snapshot_path = self._snapshots.publish(snapshot)
        self._ledger.record_snapshot(snapshot, snapshot_path)
        return BroadIndexPublication(snapshot=snapshot, manifest=manifest, row_count=len(rows))

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

    def _preserve(self, table: object) -> None:
        from ..ports import ProviderTable

        if not isinstance(table, ProviderTable):
            raise TypeError("宽基指数提供方响应类型无效")
        envelope = RawRecordEnvelope(
            provider=table.provider_id,
            interface_name=table.api_name,
            source_endpoint=table.source_endpoint,
            request_identity=table.request_identity,
            received_at=table.received_at,
            schema_version="provider-v1",
            content_hash=content_hash(table.raw_body),
        )
        self._raw.append(envelope, table.raw_body)


def _windows(start: date, end: date) -> tuple[tuple[date, date], ...]:
    result = []
    current = start
    while current <= end:
        boundary = min(end, date(current.year + 4, 12, 31))
        result.append((current, boundary))
        current = date(boundary.year + 1, 1, 1)
    return tuple(result)


def _validate_coverage(rows: tuple[object, ...], end_date: date) -> None:
    from ..contracts import BroadIndexDailyObservation

    typed = tuple(row for row in rows if isinstance(row, BroadIndexDailyObservation))
    for code in BROAD_INDEX_REGISTRY:
        values = [row for row in typed if row.instrument_id == code]
        if len(values) < 520:
            raise ValueError(f"宽基指数历史不足 520 根：{code}:{len(values)}")
        if max(row.trade_date for row in values) < end_date:
            raise ValueError(f"宽基指数目标日缺失：{code}:{end_date}")


__all__ = ["BroadIndexFoundationService", "BroadIndexPublication"]
