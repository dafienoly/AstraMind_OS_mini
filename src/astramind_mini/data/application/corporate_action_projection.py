"""Resumable WP-0002B-H4 company-action and adjusted-price publication."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from astramind_mini.contracts import DataSnapshot

from ..contracts import DatasetManifest
from ..ports import (
    CorporateActionProjector,
    DataArtifactLedger,
    FileDatasetStore,
    LegacyMarketRelease,
    ReleasableSnapshotStore,
)
from .corporate_action_publication import build_corporate_action_manifests
from .datasets import DataSnapshotBuilder
from .identity import content_hash, file_hash
from .state_files import (
    corporate_year_is_intact,
    load_state,
    save_state,
)


@dataclass(frozen=True, slots=True)
class CorporateActionPublication:
    snapshot: DataSnapshot
    manifests: tuple[DatasetManifest, ...]


class CorporateActionProjectionService:
    def __init__(
        self,
        *,
        data_root: Path,
        dataset_store: FileDatasetStore,
        snapshot_store: ReleasableSnapshotStore,
        ledger: DataArtifactLedger,
        projector: CorporateActionProjector,
    ) -> None:
        self._root = data_root
        self._dataset_store = dataset_store
        self._snapshot_store = snapshot_store
        self._ledger = ledger
        self._projector = projector

    def run(
        self,
        *,
        release: LegacyMarketRelease,
        base_snapshot_id: str,
        republish: bool = False,
    ) -> CorporateActionPublication:
        base = self._manifests(self._snapshot_store.get(base_snapshot_id))
        self._require_inputs(base)
        import_id = content_hash(
            {
                "base_snapshot_id": base_snapshot_id,
                "legacy_release": release.release_content_hash,
                "policy": "wp-0002b-h4-v2",
            }
        )
        staging = self._root / "imports" / import_id.rsplit(":", 1)[-1]
        state_path = staging / "state.json"
        state = load_state(state_path) or {
            "import_id": import_id,
            "imported_at": datetime.now(UTC).isoformat(),
            "completed_years": {},
        }
        if (snapshot_id := state.get("snapshot_id")) and not republish:
            return self._completed(str(snapshot_id))
        imported_at = datetime.fromisoformat(str(state["imported_at"]))
        action_path, action_stats = self._actions(release, staging, state, state_path, imported_at)
        factor_anchors = self._factor_anchors(base, staging, state, state_path)
        yearly = self._project_years(
            base,
            action_path,
            factor_anchors,
            staging,
            state,
            state_path,
            imported_at,
        )
        return self._publish(
            base=base,
            release=release,
            import_id=import_id,
            action_path=action_path,
            action_stats=action_stats,
            yearly=yearly,
            staging=staging,
            state=state,
            state_path=state_path,
        )

    def _actions(
        self,
        release: LegacyMarketRelease,
        staging: Path,
        state: dict[str, object],
        state_path: Path,
        imported_at: datetime,
    ) -> tuple[Path, dict[str, int]]:
        output = staging / "corporate-action.parquet"
        raw = state.get("corporate_action")
        if isinstance(raw, dict) and _artifact_is_intact(raw, output):
            return output, _stats(raw.get("stats"))
        stats = self._projector.compact_actions(
            source_files=release.files("dividend"),
            output=output,
            imported_at=imported_at,
        )
        state["corporate_action"] = {
            "path": str(output),
            "hash": file_hash(output),
            "stats": stats,
        }
        save_state(state_path, state)
        return output, stats

    def _factor_anchors(
        self,
        base: dict[str, DatasetManifest],
        staging: Path,
        state: dict[str, object],
        state_path: Path,
    ) -> Path:
        output = staging / "terminal-factor-anchors.parquet"
        raw = state.get("factor_anchors")
        if isinstance(raw, dict) and _artifact_is_intact(raw, output):
            return output
        stats = self._projector.build_factor_anchors(
            factor_files=self._all_parquet(base["adjustment_factor"]),
            output=output,
        )
        state["factor_anchors"] = {
            "path": str(output),
            "hash": file_hash(output),
            "stats": stats,
        }
        save_state(state_path, state)
        return output

    def _project_years(
        self,
        base: dict[str, DatasetManifest],
        action_path: Path,
        factor_anchors: Path,
        staging: Path,
        state: dict[str, object],
        state_path: Path,
        imported_at: datetime,
    ) -> dict[int, dict[str, object]]:
        completed = state["completed_years"]
        assert isinstance(completed, dict)
        start, end = base["daily_market"].date_range
        previous_anchor: Path | None = None
        for year in range(start.year, end.year + 1):
            existing = completed.get(str(year))
            if isinstance(existing, dict) and corporate_year_is_intact(existing):
                previous_anchor = Path(str(existing["anchor_path"]))
                continue
            output = staging / "annual" / f"adjusted-market-{year}.parquet"
            next_anchor = staging / "anchors" / f"research-index-{year}.parquet"
            stats = self._projector.project_year(
                daily_files=self._annual(base["daily_market"], year),
                factor_files=self._annual(base["adjustment_factor"], year),
                action_history=action_path,
                factor_anchors=factor_anchors,
                previous_index_anchors=previous_anchor,
                output=output,
                next_index_anchors=next_anchor,
                imported_at=imported_at,
            )
            completed[str(year)] = {
                "path": str(output),
                "hash": file_hash(output),
                "anchor_path": str(next_anchor),
                "anchor_hash": file_hash(next_anchor),
                **stats,
            }
            save_state(state_path, state)
            previous_anchor = next_anchor
        return {int(year): item for year, item in completed.items() if isinstance(item, dict)}

    def _publish(
        self,
        *,
        base: dict[str, DatasetManifest],
        release: LegacyMarketRelease,
        import_id: str,
        action_path: Path,
        action_stats: dict[str, int],
        yearly: dict[int, dict[str, object]],
        staging: Path,
        state: dict[str, object],
        state_path: Path,
    ) -> CorporateActionPublication:
        finished_at = datetime.now(UTC)
        manifests, artifacts = build_corporate_action_manifests(
            base=base,
            release=release,
            import_id=import_id,
            action_path=action_path,
            action_stats=action_stats,
            yearly=yearly,
            staging=staging,
            finished_at=finished_at,
        )
        for manifest in manifests:
            path = self._dataset_store.publish_files(manifest, artifacts[manifest.dataset_name])
            self._ledger.record_dataset(manifest, path)
        snapshot = DataSnapshotBuilder().build(
            manifests=(*base.values(), *manifests),
            as_of=finished_at,
            created_at=finished_at,
            code_identity="wp-0002b-h4-v2",
            resolved_gaps=(
                "current_name_history_not_available",
                "suspension_event_not_daily_state",
                "suspension_state_pending",
            ),
        )
        snapshot_path = self._snapshot_store.publish(snapshot)
        self._ledger.record_snapshot(snapshot, snapshot_path)
        self._snapshot_store.activate(snapshot, snapshot_path)
        for manifest in manifests:
            digest = manifest.dataset_version.rsplit(":", 1)[-1]
            path = self._root / "datasets" / manifest.dataset_name / digest / "manifest.json"
            self._dataset_store.activate(manifest, path)
        state["snapshot_id"] = snapshot.snapshot_id
        state["completed_at"] = finished_at.isoformat()
        save_state(state_path, state)
        return CorporateActionPublication(snapshot, manifests)

    def _completed(self, snapshot_id: str) -> CorporateActionPublication:
        snapshot = self._snapshot_store.get(snapshot_id)
        manifests = self._manifests(snapshot)
        selected = tuple(manifests[name] for name in ("corporate_action", "adjusted_market"))
        return CorporateActionPublication(snapshot, selected)

    def _manifests(self, snapshot: DataSnapshot) -> dict[str, DatasetManifest]:
        result = {}
        for ref in snapshot.datasets:
            digest = ref.dataset_version.rsplit(":", 1)[-1]
            path = self._root / "datasets" / ref.dataset_name / digest / "manifest.json"
            result[ref.dataset_name] = DatasetManifest.model_validate_json(
                path.read_text(encoding="utf-8")
            )
        return result

    def _artifact(self, manifest: DatasetManifest, name: str) -> Path:
        if name not in manifest.artifact_paths:
            raise ValueError(f"{manifest.dataset_name} 未声明制品 {name}")
        digest = manifest.dataset_version.rsplit(":", 1)[-1]
        return self._root / "datasets" / manifest.dataset_name / digest / name

    def _all_parquet(self, manifest: DatasetManifest) -> tuple[Path, ...]:
        return tuple(
            self._artifact(manifest, name)
            for name in manifest.artifact_paths
            if name.endswith(".parquet")
        )

    def _annual(self, manifest: DatasetManifest, year: int) -> tuple[Path, ...]:
        return tuple(
            self._artifact(manifest, name)
            for name in manifest.artifact_paths
            if name.endswith(f"-{year}.parquet")
        )

    @staticmethod
    def _require_inputs(base: dict[str, DatasetManifest]) -> None:
        required = {"security_master", "daily_market", "adjustment_factor"}
        missing = required - base.keys()
        if missing:
            raise ValueError("H4 基础快照缺少：" + ",".join(sorted(missing)))


def _artifact_is_intact(value: dict[str, object], expected: Path) -> bool:
    return expected.is_file() and value.get("hash") == file_hash(expected)


def _stats(value: object) -> dict[str, int]:
    if not isinstance(value, dict):
        raise ValueError("投影统计状态无效")
    return {str(key): int(item) for key, item in value.items()}


__all__ = ["CorporateActionProjectionService", "CorporateActionPublication"]
