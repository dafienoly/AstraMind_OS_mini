"""Resumable WP-0002B-H3 historical status publication."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from astramind_mini.contracts import DataSnapshot

from ..contracts import DatasetManifest
from ..ports import (
    DataArtifactLedger,
    FileDatasetStore,
    HistoricalStatusProjector,
    LegacyMarketRelease,
    ReleasableSnapshotStore,
)
from .datasets import DataSnapshotBuilder
from .identity import content_hash, file_hash
from .state_files import load_state, save_state, status_year_is_intact
from .status_publication import build_status_manifests


@dataclass(frozen=True, slots=True)
class StatusProjectionPublication:
    snapshot: DataSnapshot
    manifests: tuple[DatasetManifest, ...]


class StatusProjectionService:
    def __init__(
        self,
        *,
        data_root: Path,
        dataset_store: FileDatasetStore,
        snapshot_store: ReleasableSnapshotStore,
        ledger: DataArtifactLedger,
        projector: HistoricalStatusProjector,
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
    ) -> StatusProjectionPublication:
        base = self._manifests(self._snapshot_store.get(base_snapshot_id))
        self._require_inputs(base)
        import_id = content_hash(
            {
                "base_snapshot_id": base_snapshot_id,
                "legacy_release": release.release_content_hash,
                "policy": "wp-0002b-h3-v1",
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
        name_path, name_stats = self._name_history(release, staging, state, state_path, imported_at)
        yearly = self._project_years(base, name_path, staging, state, state_path, imported_at)
        return self._publish(
            base=base,
            release=release,
            import_id=import_id,
            name_path=name_path,
            name_stats=name_stats,
            yearly=yearly,
            staging=staging,
            state=state,
            state_path=state_path,
        )

    def _name_history(
        self,
        release: LegacyMarketRelease,
        staging: Path,
        state: dict[str, object],
        state_path: Path,
        imported_at: datetime,
    ) -> tuple[Path, dict[str, int]]:
        output = staging / "security-name-history.parquet"
        raw = state.get("name_history")
        if isinstance(raw, dict) and output.is_file() and raw.get("hash") == file_hash(output):
            return output, _int_stats(raw["stats"])
        stats = self._projector.compact_name_history(
            source_files=release.files("namechange"),
            output=output,
            imported_at=imported_at,
        )
        state["name_history"] = {
            "path": str(output),
            "hash": file_hash(output),
            "stats": stats,
        }
        save_state(state_path, state)
        return output, stats

    def _project_years(
        self,
        base: dict[str, DatasetManifest],
        name_path: Path,
        staging: Path,
        state: dict[str, object],
        state_path: Path,
        imported_at: datetime,
    ) -> dict[int, dict[str, object]]:
        completed = state["completed_years"]
        assert isinstance(completed, dict)
        start, end = base["daily_market"].date_range
        security = self._artifact(base["security_master"], "data.parquet")
        calendar = self._artifact(base["trade_calendar"], "data.parquet")
        for year in range(start.year, end.year + 1):
            current = completed.get(str(year))
            if isinstance(current, dict) and status_year_is_intact(current):
                continue
            output = staging / "annual" / f"daily-tradability-{year}.parquet"
            stats = self._projector.project_year(
                year=year,
                security_master=security,
                trade_calendar=calendar,
                daily_files=self._annual(base["daily_market"], year),
                price_limit_files=self._annual(base["price_limit"], year),
                suspension_files=self._annual(base["suspension_event"], year),
                name_history=name_path,
                output=output,
                imported_at=imported_at,
            )
            completed[str(year)] = {
                "path": str(output),
                "hash": file_hash(output),
                **stats,
            }
            save_state(state_path, state)
        return {int(year): item for year, item in completed.items() if isinstance(item, dict)}

    def _publish(
        self,
        *,
        base: dict[str, DatasetManifest],
        release: LegacyMarketRelease,
        import_id: str,
        name_path: Path,
        name_stats: dict[str, int],
        yearly: dict[int, dict[str, object]],
        staging: Path,
        state: dict[str, object],
        state_path: Path,
    ) -> StatusProjectionPublication:
        finished_at = datetime.now(UTC)
        manifests, artifacts = build_status_manifests(
            base=base,
            release=release,
            import_id=import_id,
            name_path=name_path,
            name_stats=name_stats,
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
            code_identity="wp-0002b-h3-v1",
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
        return StatusProjectionPublication(snapshot, manifests)

    def _completed(self, snapshot_id: str) -> StatusProjectionPublication:
        snapshot = self._snapshot_store.get(snapshot_id)
        manifests = self._manifests(snapshot)
        selected = tuple(manifests[name] for name in ("security_name_history", "daily_tradability"))
        return StatusProjectionPublication(snapshot, selected)

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

    def _annual(self, manifest: DatasetManifest, year: int) -> tuple[Path, ...]:
        names = tuple(name for name in manifest.artifact_paths if name.endswith(f"-{year}.parquet"))
        return tuple(self._artifact(manifest, name) for name in names)

    @staticmethod
    def _require_inputs(base: dict[str, DatasetManifest]) -> None:
        required = {
            "security_master",
            "trade_calendar",
            "daily_market",
            "price_limit",
            "suspension_event",
        }
        missing = required - base.keys()
        if missing:
            raise ValueError("H3 基础快照缺少：" + ",".join(sorted(missing)))


def _int_stats(value: object) -> dict[str, int]:
    if not isinstance(value, dict):
        raise ValueError("名称历史统计状态无效")
    return {str(key): int(item) for key, item in value.items()}


__all__ = ["StatusProjectionPublication", "StatusProjectionService"]
