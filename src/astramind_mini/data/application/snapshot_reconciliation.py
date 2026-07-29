"""Recover selected immutable datasets without refetching provider data."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from astramind_mini.contracts import DataSnapshot

from ..contracts import DatasetManifest
from ..ports import DataArtifactLedger, FileDatasetStore, ReleasableSnapshotStore
from .daily_pipeline_support import load_snapshot_bundle
from .datasets import DataSnapshotBuilder


@dataclass(frozen=True, slots=True)
class SnapshotReconciliation:
    snapshot: DataSnapshot
    restored_datasets: tuple[str, ...]


class SnapshotDatasetReconciler:
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

    def restore(
        self,
        *,
        base_snapshot_id: str,
        donor_snapshot_id: str,
        dataset_names: tuple[str, ...],
        created_at: datetime,
        code_identity: str,
        donor_gap_prefixes: tuple[str, ...] = (),
    ) -> SnapshotReconciliation:
        if created_at.tzinfo is None:
            raise ValueError("快照修复时间必须带时区")
        if not dataset_names or len(dataset_names) != len(set(dataset_names)):
            raise ValueError("待恢复数据集必须非空且不可重复")
        base, manifests, _ = load_snapshot_bundle(self._root, base_snapshot_id)
        donor, donor_manifests, _ = load_snapshot_bundle(self._root, donor_snapshot_id)
        missing = tuple(sorted(set(dataset_names) - set(donor_manifests)))
        if missing:
            raise ValueError("捐赠快照缺少数据集：" + ",".join(missing))
        restored = {name: donor_manifests[name] for name in dataset_names}
        manifests.update(restored)
        inherited_donor_gaps = tuple(
            gap
            for gap in donor.known_gaps
            if any(gap.startswith(prefix) for prefix in donor_gap_prefixes)
        )
        snapshot = DataSnapshotBuilder().build(
            manifests=tuple(manifests.values()),
            as_of=max(base.as_of, donor.as_of),
            created_at=created_at,
            code_identity=code_identity,
            known_gaps=(*base.known_gaps, *inherited_donor_gaps),
        )
        path = self._snapshots.publish(snapshot)
        self._ledger.record_snapshot(snapshot, path)
        self._snapshots.activate(
            snapshot,
            path,
            expected_snapshot_id=base.snapshot_id,
        )
        for manifest in restored.values():
            self._datasets.activate(manifest, self._manifest_path(manifest))
        return SnapshotReconciliation(
            snapshot=snapshot,
            restored_datasets=tuple(sorted(restored)),
        )

    def _manifest_path(self, manifest: DatasetManifest) -> Path:
        digest = manifest.dataset_version.removeprefix("sha256:")
        return self._root / "datasets" / manifest.dataset_name / digest / "manifest.json"


__all__ = ["SnapshotDatasetReconciler", "SnapshotReconciliation"]
