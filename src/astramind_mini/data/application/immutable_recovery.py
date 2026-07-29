"""Local-only republication of suspect immutable dataset artifacts."""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import cast

import duckdb

from astramind_mini.contracts import DataSnapshot

from ..contracts import DatasetManifest
from ..ports import DataArtifactLedger, FileDatasetStore, ReleasableSnapshotStore
from .daily_pipeline_support import load_snapshot_bundle
from .datasets import DataSnapshotBuilder, build_dataset_manifest_from_hashes
from .identity import canonical_json, content_hash, file_hash


@dataclass(frozen=True, slots=True)
class ImmutableRecoveryResult:
    snapshot: DataSnapshot
    recovered_datasets: tuple[str, ...]
    recovery_report_path: Path


class ImmutableArtifactRecoveryService:
    """Republish explicit local files under new identities and atomically switch a snapshot."""

    def __init__(
        self,
        *,
        data_root: Path,
        datasets: FileDatasetStore,
        snapshots: ReleasableSnapshotStore,
        ledger: DataArtifactLedger,
    ) -> None:
        self._root = data_root
        self._datasets = datasets
        self._snapshots = snapshots
        self._ledger = ledger

    def recover(
        self,
        *,
        base_snapshot_id: str,
        dataset_sources: Mapping[str, Mapping[str, Path]],
        created_at: datetime,
        code_identity: str,
    ) -> ImmutableRecoveryResult:
        if created_at.tzinfo is None:
            raise ValueError("快照恢复时间必须带时区")
        if not dataset_sources:
            raise ValueError("至少需要恢复一个数据集")
        base, manifests, _ = load_snapshot_bundle(self._root, base_snapshot_id)
        missing = tuple(sorted(set(dataset_sources) - set(manifests)))
        if missing:
            raise ValueError("基础快照缺少待恢复数据集：" + ",".join(missing))

        previous_manifests = {name: manifests[name] for name in dataset_sources}
        replacements: dict[str, DatasetManifest] = {}
        manifest_paths: dict[str, Path] = {}
        for dataset_name, sources in sorted(dataset_sources.items()):
            previous = manifests[dataset_name]
            replacement = _replacement_manifest(
                previous=previous,
                sources=sources,
                recovered_at=created_at,
            )
            path = self._datasets.publish_files(
                replacement,
                {name: (source, file_hash(source)) for name, source in sorted(sources.items())},
            )
            self._ledger.record_dataset(replacement, path)
            replacements[dataset_name] = replacement
            manifest_paths[dataset_name] = path

        manifests.update(replacements)
        snapshot = DataSnapshotBuilder().build(
            manifests=tuple(manifests.values()),
            as_of=base.as_of,
            created_at=created_at,
            code_identity=code_identity,
            known_gaps=base.known_gaps,
        )
        snapshot_path = self._snapshots.publish(snapshot)
        self._ledger.record_snapshot(snapshot, snapshot_path)
        report_path = _write_recovery_report(
            root=self._root,
            base=base,
            replacement=snapshot,
            previous_manifests=previous_manifests,
            replacement_manifests=replacements,
            created_at=created_at,
        )
        self._snapshots.activate(
            snapshot,
            snapshot_path,
            expected_snapshot_id=base.snapshot_id,
        )
        for dataset_name, manifest in replacements.items():
            self._datasets.activate(manifest, manifest_paths[dataset_name])
        return ImmutableRecoveryResult(
            snapshot=snapshot,
            recovered_datasets=tuple(sorted(replacements)),
            recovery_report_path=report_path,
        )


def _replacement_manifest(
    *,
    previous: DatasetManifest,
    sources: Mapping[str, Path],
    recovered_at: datetime,
) -> DatasetManifest:
    if tuple(sorted(sources)) != tuple(sorted(previous.artifact_paths)):
        raise ValueError(f"恢复文件与旧清单不一致：{previous.dataset_name}")
    for source in sources.values():
        if not source.is_file():
            raise FileNotFoundError(source)
    artifact_hashes = {name: file_hash(path) for name, path in sorted(sources.items())}
    row_count, observed_range = _parquet_stats(previous, sources)
    return build_dataset_manifest_from_hashes(
        dataset_name=previous.dataset_name,
        schema_version=previous.schema_version,
        provider=previous.provider,
        source_endpoint=previous.source_endpoint,
        request_identity=content_hash(
            {
                "operation": "immutable-artifact-recovery-v1",
                "previous_dataset_version": previous.dataset_version,
                "artifact_hashes": artifact_hashes,
            }
        ),
        retrieved_at=recovered_at,
        market_timezone=previous.market_timezone,
        date_range=observed_range or previous.date_range,
        universe=previous.universe,
        primary_key=previous.primary_key,
        availability_rule=previous.availability_rule,
        units=previous.units,
        row_count=row_count if row_count is not None else previous.row_count,
        artifact_hashes=artifact_hashes,
        known_gaps=previous.known_gaps,
        critical_gaps=previous.critical_gaps,
        provider_lineage=previous.provider_lineage,
    )


def _parquet_stats(
    manifest: DatasetManifest,
    sources: Mapping[str, Path],
) -> tuple[int | None, tuple[date, date] | None]:
    paths = tuple(path for name, path in sorted(sources.items()) if name.endswith(".parquet"))
    if not paths:
        return None, None
    with duckdb.connect(":memory:") as connection:
        path_values = [str(path) for path in paths]
        columns = {
            str(row[0])
            for row in connection.execute(
                "DESCRIBE SELECT * FROM read_parquet(?, union_by_name=true)",
                [path_values],
            ).fetchall()
        }
        missing = tuple(key for key in manifest.primary_key if key not in columns)
        if missing:
            raise ValueError("恢复制品缺少主键列：" + ",".join(missing))
        keys = ", ".join(_quoted(key) for key in manifest.primary_key)
        counts = connection.execute(
            f"SELECT count(*), count(DISTINCT ({keys})) FROM read_parquet(?, union_by_name=true)",
            [path_values],
        ).fetchone()
        assert counts is not None
        if int(counts[0]) != int(counts[1]):
            raise ValueError(f"恢复制品主键不唯一：{manifest.dataset_name}")
        date_column = next(
            (
                key
                for key in manifest.primary_key
                if key
                in {
                    "trade_date",
                    "calendar_date",
                    "market_date",
                    "nav_date",
                    "reporting_period",
                }
            ),
            None,
        )
        if date_column is None or not int(counts[0]):
            return int(counts[0]), None
        dates = connection.execute(
            f"SELECT min({_quoted(date_column)}), max({_quoted(date_column)}) "
            "FROM read_parquet(?, union_by_name=true)",
            [path_values],
        ).fetchone()
        assert dates is not None
        return int(counts[0]), (cast(date, dates[0]), cast(date, dates[1]))


def _write_recovery_report(
    *,
    root: Path,
    base: DataSnapshot,
    replacement: DataSnapshot,
    previous_manifests: Mapping[str, DatasetManifest],
    replacement_manifests: Mapping[str, DatasetManifest],
    created_at: datetime,
) -> Path:
    payload = {
        "report_version": "immutable-artifact-recovery-v1",
        "base_snapshot_id": base.snapshot_id,
        "replacement_snapshot_id": replacement.snapshot_id,
        "created_at": created_at,
        "datasets": [
            {
                "dataset_name": name,
                "previous_dataset_version": previous_manifests[name].dataset_version,
                "previous_content_hash": previous_manifests[name].content_hash,
                "replacement_dataset_version": replacement_manifests[name].dataset_version,
                "replacement_content_hash": replacement_manifests[name].content_hash,
            }
            for name in sorted(replacement_manifests)
        ],
        "broker_actions_allowed": False,
    }
    encoded = canonical_json(payload)
    report_id = content_hash(payload).rsplit(":", 1)[-1]
    path = root / "recoveries" / report_id / "report.json"
    if path.exists():
        if path.read_bytes() != encoded:
            raise ValueError("恢复报告身份冲突")
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=".report.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return path


def _quoted(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def load_recovery_plan(path: Path) -> tuple[str, dict[str, dict[str, Path]]]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or not isinstance(value.get("base_snapshot_id"), str):
        raise ValueError("恢复计划缺少 base_snapshot_id")
    raw_datasets = value.get("datasets")
    if not isinstance(raw_datasets, dict) or not raw_datasets:
        raise ValueError("恢复计划缺少 datasets")
    datasets: dict[str, dict[str, Path]] = {}
    for dataset_name, artifacts in raw_datasets.items():
        if not isinstance(dataset_name, str) or not isinstance(artifacts, dict):
            raise ValueError("恢复计划 datasets 格式无效")
        datasets[dataset_name] = {
            str(name): Path(str(source)).expanduser().resolve()
            for name, source in artifacts.items()
        }
    return str(value["base_snapshot_id"]), datasets


__all__ = [
    "ImmutableArtifactRecoveryService",
    "ImmutableRecoveryResult",
    "load_recovery_plan",
]
