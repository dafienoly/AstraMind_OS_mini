"""Publish validated MiniQMT extensions into the immutable DataSnapshot."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from pydantic import BaseModel

from astramind_mini.contracts import DataSnapshot

from ..contracts import DatasetManifest
from ..contracts.source import ProviderBatch
from ..ports import (
    DataArtifactLedger,
    DatasetStore,
    ParquetEncoder,
    SnapshotStore,
)
from .datasets import DataSnapshotBuilder, build_dataset_manifest


@dataclass(frozen=True, slots=True)
class ExtendedDatasetSpec:
    dataset_name: str
    schema_version: str
    columns: tuple[tuple[str, str], ...]
    primary_key: tuple[str, ...]
    date_range: tuple[date, date]
    universe: tuple[str, ...]
    availability_rule: str
    units: tuple[str, ...]
    known_gaps: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ExtendedDatasetPublication:
    manifest: DatasetManifest
    snapshot: DataSnapshot


class ExtendedDatasetPublisher:
    def __init__(
        self,
        *,
        data_root: Path,
        encoder: ParquetEncoder,
        datasets: DatasetStore,
        snapshots: SnapshotStore,
        ledger: DataArtifactLedger,
    ) -> None:
        self._root = data_root
        self._encoder = encoder
        self._datasets = datasets
        self._snapshots = snapshots
        self._ledger = ledger

    def publish(
        self,
        *,
        base_snapshot_id: str,
        spec: ExtendedDatasetSpec,
        rows: Sequence[BaseModel],
        batch: ProviderBatch,
        as_of: datetime,
    ) -> ExtendedDatasetPublication:
        if not rows:
            raise ValueError(f"{spec.dataset_name} 没有可发布观察")
        if any(getattr(row, "provider", None) != batch.provider_id for row in rows):
            raise ValueError("同一数据集版本不得混用提供方")
        if any(getattr(row, "available_at", as_of) > as_of for row in rows):
            raise ValueError("数据集包含晚于快照时点才可用的观察")
        artifact_name = f"{spec.dataset_name}.parquet"
        payload = self._encoder.encode(rows, spec.columns)
        manifest = build_dataset_manifest(
            dataset_name=spec.dataset_name,
            schema_version=spec.schema_version,
            provider=batch.provider_id,
            source_endpoint=batch.source_endpoint,
            request_identity=batch.request_identity,
            retrieved_at=batch.retrieved_at,
            market_timezone="Asia/Shanghai",
            date_range=spec.date_range,
            universe=spec.universe,
            primary_key=spec.primary_key,
            availability_rule=spec.availability_rule,
            units=spec.units,
            row_count=len(rows),
            artifacts={artifact_name: payload},
            known_gaps=spec.known_gaps,
        )
        manifest_path = self._datasets.publish(manifest, {artifact_name: payload})
        self._ledger.record_dataset(manifest, manifest_path)
        base = self._snapshots.get(base_snapshot_id)
        manifests = self._base_manifests(base)
        manifests[spec.dataset_name] = manifest
        snapshot = DataSnapshotBuilder().build(
            manifests=tuple(manifests.values()),
            as_of=max(base.as_of, as_of),
            created_at=max(batch.retrieved_at, as_of),
            code_identity="miniqmt-extended-datasets-v1",
            known_gaps=base.known_gaps,
        )
        snapshot_path = self._snapshots.publish(snapshot)
        self._ledger.record_snapshot(snapshot, snapshot_path)
        return ExtendedDatasetPublication(manifest=manifest, snapshot=snapshot)

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


__all__ = [
    "ExtendedDatasetPublication",
    "ExtendedDatasetPublisher",
    "ExtendedDatasetSpec",
]
