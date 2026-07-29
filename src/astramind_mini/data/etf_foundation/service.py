"""Publish the bounded ETF research foundation into one immutable snapshot."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from pydantic import BaseModel

from astramind_mini.contracts import DataSnapshot
from astramind_mini.data.application.datasets import (
    DataSnapshotBuilder,
    build_dataset_manifest,
)
from astramind_mini.data.application.identity import content_hash
from astramind_mini.data.contracts import DatasetManifest, RawRecordEnvelope
from astramind_mini.data.ports import (
    DataArtifactLedger,
    FileDatasetStore,
    HistoricalMarketDataProvider,
    ParquetEncoder,
    ProviderTable,
    RawRecordStore,
    ReleasableSnapshotStore,
)

from .contracts import (
    EtfDailyObservation,
    EtfIndustryMappingObservation,
    EtfMasterObservation,
    EtfShareObservation,
)
from .normalization import (
    mapping_observations,
    normalize_daily,
    normalize_master,
    normalize_share,
)
from .registry import ETF_CODES, MAPPING_VERSION, validate_registry
from .schemas import (
    ETF_DAILY_COLUMNS,
    ETF_MAPPING_COLUMNS,
    ETF_MASTER_COLUMNS,
    ETF_SHARE_COLUMNS,
)

MASTER_FIELDS = (
    "ts_code",
    "name",
    "fund_type",
    "invest_type",
    "benchmark",
    "found_date",
    "list_date",
    "delist_date",
    "status",
    "market",
)
DAILY_FIELDS = (
    "ts_code",
    "trade_date",
    "pre_close",
    "open",
    "high",
    "low",
    "close",
    "change",
    "pct_chg",
    "vol",
    "amount",
)
SHARE_FIELDS = ("ts_code", "trade_date", "fd_share")


@dataclass(frozen=True, slots=True)
class EtfFoundationPublication:
    snapshot: DataSnapshot
    manifests: tuple[DatasetManifest, ...]
    row_counts: dict[str, int]
    activated: bool


@dataclass(frozen=True, slots=True)
class EtfFoundationPrepared:
    manifests: tuple[DatasetManifest, ...]
    manifest_paths: dict[str, Path]
    row_counts: dict[str, int]
    retrieved_at: datetime
    known_gaps: tuple[str, ...]
    resolved_gaps: tuple[str, ...]


class EtfFoundationService:
    def __init__(
        self,
        *,
        data_root: Path,
        provider: HistoricalMarketDataProvider,
        raw_store: RawRecordStore,
        encoder: ParquetEncoder,
        dataset_store: FileDatasetStore,
        snapshot_store: ReleasableSnapshotStore,
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
        activate: bool = False,
    ) -> EtfFoundationPublication:
        prepared = await self.prepare(
            base_snapshot_id=base_snapshot_id,
            start_date=start_date,
            end_date=end_date,
        )
        base = self._snapshots.get(base_snapshot_id)
        all_manifests = self._base_manifests(base)
        all_manifests.update({item.dataset_name: item for item in prepared.manifests})
        snapshot = DataSnapshotBuilder().build(
            manifests=tuple(all_manifests.values()),
            as_of=max(base.as_of, prepared.retrieved_at),
            created_at=prepared.retrieved_at,
            code_identity="wp-0043-etf-foundation-v1",
            known_gaps=(*base.known_gaps, *prepared.known_gaps),
            resolved_gaps=prepared.resolved_gaps,
        )
        snapshot_path = self._snapshots.publish(snapshot)
        self._ledger.record_snapshot(snapshot, snapshot_path)
        if activate:
            for manifest in prepared.manifests:
                self._datasets.activate(
                    manifest,
                    prepared.manifest_paths[manifest.dataset_name],
                )
            self._snapshots.activate(
                snapshot,
                snapshot_path,
                expected_snapshot_id=base.snapshot_id,
            )
        return EtfFoundationPublication(
            snapshot=snapshot,
            manifests=prepared.manifests,
            row_counts=prepared.row_counts,
            activated=activate,
        )

    async def prepare(
        self,
        *,
        base_snapshot_id: str,
        start_date: date,
        end_date: date,
    ) -> EtfFoundationPrepared:
        if start_date > end_date:
            raise ValueError("ETF 数据开始日期不能晚于结束日期")
        validate_registry()
        master_table = await self._provider.query(
            "fund_basic",
            params={"market": "E"},
            fields=MASTER_FIELDS,
        )
        self._preserve(master_table)
        masters = normalize_master(master_table)
        daily, shares, retrieved_at = await self._history(
            start_date=start_date,
            end_date=end_date,
            retrieved_at=master_table.received_at,
        )
        _validate_history(daily, shares, end_date=end_date)
        mappings = mapping_observations(retrieved_at)
        payloads = self._payloads(masters, daily, shares, mappings)
        request = content_hash(
            {
                "base_snapshot_id": base_snapshot_id,
                "start_date": start_date,
                "end_date": end_date,
                "mapping_version": MAPPING_VERSION,
                "etf_codes": ETF_CODES,
            }
        )
        manifests = self._manifests(
            payloads=payloads,
            request_identity=request,
            retrieved_at=retrieved_at,
            masters=masters,
            daily=daily,
            shares=shares,
            mappings=mappings,
        )
        manifest_paths = {}
        for manifest in manifests:
            artifacts = {
                name: payloads[manifest.dataset_name][1] for name in manifest.artifact_paths
            }
            path = self._datasets.publish(manifest, artifacts)
            self._ledger.record_dataset(manifest, path)
            manifest_paths[manifest.dataset_name] = path
        freshness_gap = "etf_daily_latest_before_requested_cutoff"
        is_fresh = max(row.trade_date for row in daily) >= end_date
        return EtfFoundationPrepared(
            manifests=manifests,
            manifest_paths=manifest_paths,
            row_counts={name: len(values[0]) for name, values in payloads.items()},
            retrieved_at=retrieved_at,
            known_gaps=(
                "etf_mapping_not_point_in_time_before_2026-07-29",
                "etf_spread_not_in_foundation",
                "etf_tracking_error_not_in_foundation",
                "etf_tradability_not_in_foundation",
                "etf_share_historical_availability_uses_retrieval_time",
                *((freshness_gap,) if not is_fresh else ()),
            ),
            resolved_gaps=(freshness_gap,) if is_fresh else (),
        )

    async def _history(
        self,
        *,
        start_date: date,
        end_date: date,
        retrieved_at: datetime,
    ) -> tuple[tuple[EtfDailyObservation, ...], tuple[EtfShareObservation, ...], datetime]:
        daily: list[EtfDailyObservation] = []
        shares: list[EtfShareObservation] = []
        for code in ETF_CODES:
            params = {
                "ts_code": code,
                "start_date": f"{start_date:%Y%m%d}",
                "end_date": f"{end_date:%Y%m%d}",
            }
            daily_table = await self._provider.query(
                "fund_daily", params=params, fields=DAILY_FIELDS
            )
            share_table = await self._provider.query(
                "fund_share", params=params, fields=SHARE_FIELDS
            )
            self._preserve(daily_table)
            self._preserve(share_table)
            daily.extend(normalize_daily(daily_table))
            shares.extend(normalize_share(share_table))
            retrieved_at = max(
                retrieved_at,
                daily_table.received_at,
                share_table.received_at,
            )
        return tuple(daily), tuple(shares), retrieved_at

    def _payloads(
        self,
        masters: tuple[EtfMasterObservation, ...],
        daily: tuple[EtfDailyObservation, ...],
        shares: tuple[EtfShareObservation, ...],
        mappings: tuple[EtfIndustryMappingObservation, ...],
    ) -> dict[str, tuple[tuple[BaseModel, ...], bytes]]:
        return {
            "etf_master": (masters, self._encoder.encode(masters, ETF_MASTER_COLUMNS)),
            "etf_daily": (daily, self._encoder.encode(daily, ETF_DAILY_COLUMNS)),
            "etf_share": (shares, self._encoder.encode(shares, ETF_SHARE_COLUMNS)),
            "etf_industry_mapping": (
                mappings,
                self._encoder.encode(mappings, ETF_MAPPING_COLUMNS),
            ),
        }

    def _manifests(
        self,
        *,
        payloads: dict[str, tuple[tuple[BaseModel, ...], bytes]],
        request_identity: str,
        retrieved_at: datetime,
        masters: tuple[EtfMasterObservation, ...],
        daily: tuple[EtfDailyObservation, ...],
        shares: tuple[EtfShareObservation, ...],
        mappings: tuple[EtfIndustryMappingObservation, ...],
    ) -> tuple[DatasetManifest, ...]:
        definitions = (
            (
                "etf_master",
                masters,
                ("instrument_id",),
                (min(row.list_date for row in masters), max(row.list_date for row in masters)),
                ("status:provider",),
                "provider master fields available by retrieval time",
            ),
            (
                "etf_daily",
                daily,
                ("instrument_id", "trade_date"),
                (min(row.trade_date for row in daily), max(row.trade_date for row in daily)),
                ("price:CNY", "volume:lots", "amount:CNY"),
                "trade_date 18:00 Asia/Shanghai",
            ),
            (
                "etf_share",
                shares,
                ("instrument_id", "trade_date"),
                (min(row.trade_date for row in shares), max(row.trade_date for row in shares)),
                ("fund_share:shares",),
                "provider retrieval time; historical publication time unavailable",
            ),
            (
                "etf_industry_mapping",
                mappings,
                ("industry_code", "etf_code", "effective_from"),
                (mappings[0].effective_from, mappings[0].effective_from),
                ("semantic_tier:versioned",),
                "effective_from 18:00 Asia/Shanghai",
            ),
        )
        return tuple(
            build_dataset_manifest(
                dataset_name=name,
                schema_version="1.0.0",
                provider=rows[0].provider,
                source_endpoint=rows[0].source_endpoint,
                request_identity=request_identity,
                retrieved_at=retrieved_at,
                market_timezone="Asia/Shanghai",
                date_range=date_range,
                universe=ETF_CODES if name != "etf_industry_mapping" else (),
                primary_key=primary_key,
                availability_rule=availability,
                units=units,
                row_count=len(rows),
                artifacts={f"{name}.parquet": payloads[name][1]},
            )
            for name, rows, primary_key, date_range, units, availability in definitions
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

    def _preserve(self, table: ProviderTable) -> None:
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


def _validate_history(
    daily: tuple[EtfDailyObservation, ...],
    shares: tuple[EtfShareObservation, ...],
    *,
    end_date: date,
) -> None:
    daily_codes = {row.instrument_id for row in daily}
    share_codes = {row.instrument_id for row in shares}
    if missing := set(ETF_CODES) - daily_codes:
        raise ValueError("ETF 白名单缺少日线：" + ",".join(sorted(missing)))
    if missing := set(ETF_CODES) - share_codes:
        raise ValueError("ETF 白名单缺少份额：" + ",".join(sorted(missing)))
    if max(row.trade_date for row in daily) > end_date:
        raise ValueError("ETF 日线包含截止日后的记录")
    if max(row.trade_date for row in shares) > end_date:
        raise ValueError("ETF 份额包含截止日后的记录")


__all__ = [
    "EtfFoundationPrepared",
    "EtfFoundationPublication",
    "EtfFoundationService",
]
