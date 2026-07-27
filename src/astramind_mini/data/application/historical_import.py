"""Minimal, resumable import of legacy daily bars and adjustment factors."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

import duckdb

from astramind_mini.contracts import DataSnapshot

from ..contracts import DatasetManifest
from ..ports import (
    AnnualMarketCompactor,
    DataArtifactLedger,
    FileDatasetStore,
    HistoricalMarketDataProvider,
    LegacyMarketRelease,
    ParquetEncoder,
    RawRecordStore,
    ReleasableSnapshotStore,
)
from .datasets import DataSnapshotBuilder
from .historical_publication import build_historical_manifests
from .historical_supplements import HistoricalSupplementService
from .identity import content_hash, file_hash
from .state_files import load_state, save_state, year_is_intact


@dataclass(frozen=True, slots=True)
class HistoricalImportPublication:
    snapshot: DataSnapshot
    daily_manifest: DatasetManifest
    factor_manifest: DatasetManifest
    imported_sessions: int
    fetched_sessions: tuple[date, ...]


class HistoricalImportService:
    def __init__(
        self,
        *,
        data_root: Path,
        provider: HistoricalMarketDataProvider,
        raw_store: RawRecordStore,
        dataset_store: FileDatasetStore,
        snapshot_store: ReleasableSnapshotStore,
        ledger: DataArtifactLedger,
        compactor: AnnualMarketCompactor,
        encoder: ParquetEncoder,
    ) -> None:
        self._root = data_root
        self._provider = provider
        self._raw_store = raw_store
        self._dataset_store = dataset_store
        self._snapshot_store = snapshot_store
        self._ledger = ledger
        self._compactor = compactor
        self._supplement_service = HistoricalSupplementService(
            provider=provider,
            raw_store=raw_store,
            encoder=encoder,
        )

    async def run(
        self,
        *,
        release: LegacyMarketRelease,
        base_snapshot_id: str,
        start_date: date = date(2000, 1, 1),
    ) -> HistoricalImportPublication:
        base_snapshot = self._snapshot_store.get(base_snapshot_id)
        base_manifests = self._base_manifests(base_snapshot)
        end_date = base_manifests["daily_market"].date_range[1]
        expected_dates = self._expected_dates(
            base_manifests["trade_calendar"],
            start_date,
            end_date,
        )
        import_id = content_hash(
            {
                "base_snapshot_id": base_snapshot_id,
                "legacy_release": release.release_content_hash,
                "start_date": start_date,
                "end_date": end_date,
                "policy": "wp-0002b-h1-v1",
            }
        )
        staging = self._root / "imports" / import_id.rsplit(":", 1)[-1]
        state_path = staging / "state.json"
        state = load_state(state_path) or {
            "import_id": import_id,
            "imported_at": datetime.now(UTC).isoformat(),
            "completed_years": {},
            "supplements": {},
        }
        if snapshot_id := state.get("snapshot_id"):
            return self._completed_publication(str(snapshot_id), state, expected_dates)
        imported_at = datetime.fromisoformat(str(state["imported_at"]))
        missing_daily = expected_dates - _parse_dates(release.dates("daily"))
        missing_factors = expected_dates - _parse_dates(release.dates("adj_factor"))
        fetched = tuple(sorted(missing_daily | missing_factors))
        await self._supplement_service.prepare(
            staging=staging,
            state=state,
            state_path=state_path,
            missing_daily=missing_daily,
            missing_factors=missing_factors,
        )
        yearly = self._compact_years(
            release,
            expected_dates,
            staging,
            state,
            state_path,
            imported_at,
        )
        return self._publish(
            release=release,
            base_manifests=base_manifests,
            import_id=import_id,
            expected_dates=expected_dates,
            yearly=yearly,
            staging=staging,
            state=state,
            state_path=state_path,
            fetched=fetched,
        )

    def _publish(
        self,
        *,
        release: LegacyMarketRelease,
        base_manifests: dict[str, DatasetManifest],
        import_id: str,
        expected_dates: frozenset[date],
        yearly: dict[int, dict[str, object]],
        staging: Path,
        state: dict[str, object],
        state_path: Path,
        fetched: tuple[date, ...],
    ) -> HistoricalImportPublication:
        finished_at = datetime.now(UTC)
        daily_manifest, factor_manifest, artifacts = build_historical_manifests(
            base=base_manifests,
            release=release,
            import_id=import_id,
            expected_dates=expected_dates,
            yearly=yearly,
            staging=staging,
            finished_at=finished_at,
        )
        daily_path = self._dataset_store.publish_files(
            daily_manifest,
            artifacts["daily_market"],
        )
        factor_path = self._dataset_store.publish_files(
            factor_manifest,
            artifacts["adjustment_factor"],
        )
        self._ledger.record_dataset(daily_manifest, daily_path)
        self._ledger.record_dataset(factor_manifest, factor_path)
        snapshot = DataSnapshotBuilder().build(
            manifests=(
                base_manifests["security_master"],
                base_manifests["trade_calendar"],
                daily_manifest,
                factor_manifest,
            ),
            as_of=finished_at,
            created_at=finished_at,
            code_identity="wp-0002b-h1-v1",
        )
        snapshot_path = self._snapshot_store.publish(snapshot)
        self._ledger.record_snapshot(snapshot, snapshot_path)
        self._snapshot_store.activate(snapshot, snapshot_path)
        self._dataset_store.activate(daily_manifest, daily_path)
        self._dataset_store.activate(factor_manifest, factor_path)
        state["snapshot_id"] = snapshot.snapshot_id
        state["completed_at"] = finished_at.isoformat()
        save_state(state_path, state)
        return HistoricalImportPublication(
            snapshot=snapshot,
            daily_manifest=daily_manifest,
            factor_manifest=factor_manifest,
            imported_sessions=len(expected_dates),
            fetched_sessions=fetched,
        )

    def _completed_publication(
        self,
        snapshot_id: str,
        state: dict[str, object],
        expected_dates: frozenset[date],
    ) -> HistoricalImportPublication:
        snapshot = self._snapshot_store.get(snapshot_id)
        manifests = self._base_manifests(snapshot)
        supplements = state.get("supplements", {})
        if not isinstance(supplements, dict):
            raise ValueError("导入补充状态格式无效")
        return HistoricalImportPublication(
            snapshot=snapshot,
            daily_manifest=manifests["daily_market"],
            factor_manifest=manifests["adjustment_factor"],
            imported_sessions=len(expected_dates),
            fetched_sessions=tuple(sorted(date.fromisoformat(day) for day in supplements)),
        )

    def _base_manifests(self, snapshot: DataSnapshot) -> dict[str, DatasetManifest]:
        manifests = {}
        for reference in snapshot.datasets:
            digest = reference.dataset_version.rsplit(":", 1)[-1]
            path = self._root / "datasets" / reference.dataset_name / digest / "manifest.json"
            manifests[reference.dataset_name] = DatasetManifest.model_validate_json(
                path.read_text(encoding="utf-8")
            )
        return manifests

    def _expected_dates(
        self,
        calendar: DatasetManifest,
        start_date: date,
        end_date: date,
    ) -> frozenset[date]:
        digest = calendar.dataset_version.rsplit(":", 1)[-1]
        path = self._root / "datasets" / calendar.dataset_name / digest / "data.parquet"
        with duckdb.connect(":memory:") as connection:
            rows = connection.execute(
                """
                SELECT DISTINCT calendar_date
                FROM read_parquet(?)
                WHERE is_open AND calendar_date BETWEEN ? AND ?
                ORDER BY calendar_date
                """,
                [str(path), start_date, end_date],
            ).fetchall()
        return frozenset(row[0] for row in rows)

    def _compact_years(
        self,
        release: LegacyMarketRelease,
        expected_dates: frozenset[date],
        staging: Path,
        state: dict[str, object],
        state_path: Path,
        imported_at: datetime,
    ) -> dict[int, dict[str, object]]:
        completed = state["completed_years"]
        assert isinstance(completed, dict)
        supplements = state["supplements"]
        assert isinstance(supplements, dict)
        for year in sorted({item.year for item in expected_dates}):
            key = str(year)
            existing = completed.get(key)
            if isinstance(existing, dict) and year_is_intact(existing):
                continue
            daily_output = staging / "annual" / "daily_market" / f"daily-market-{year}.parquet"
            factor_output = (
                staging / "annual" / "adjustment_factor" / f"adjustment-factor-{year}.parquet"
            )
            daily_supplements = _supplement_paths(supplements, year, "daily")
            factor_supplements = _supplement_paths(supplements, year, "adj_factor")
            daily_rows, _ = self._compactor.compact(
                table="daily",
                source_files=release.files_for_year("daily", year),
                supplement_files=daily_supplements,
                output=daily_output,
                imported_at=imported_at,
            )
            factor_rows, _ = self._compactor.compact(
                table="adj_factor",
                source_files=release.files_for_year("adj_factor", year),
                supplement_files=factor_supplements,
                output=factor_output,
                imported_at=imported_at,
            )
            _, factor_only = self._compactor.validate_pair(daily_output, factor_output)
            completed[key] = {
                "daily_path": str(daily_output),
                "daily_hash": file_hash(daily_output),
                "daily_rows": daily_rows,
                "factor_path": str(factor_output),
                "factor_hash": file_hash(factor_output),
                "factor_rows": factor_rows,
                "factor_only": factor_only,
                "sessions": sum(1 for item in expected_dates if item.year == year),
            }
            save_state(state_path, state)
        return {int(year): value for year, value in completed.items() if isinstance(value, dict)}


def _parse_dates(values: frozenset[str]) -> frozenset[date]:
    return frozenset(date.fromisoformat(value) for value in values)


def _supplement_paths(
    supplements: dict[str, object],
    year: int,
    field: str,
) -> tuple[Path, ...]:
    paths = []
    for day, raw_entry in supplements.items():
        if date.fromisoformat(day).year != year or not isinstance(raw_entry, dict):
            continue
        if value := raw_entry.get(field):
            paths.append(Path(str(value)))
    return tuple(sorted(paths))


__all__ = ["HistoricalImportPublication", "HistoricalImportService"]
