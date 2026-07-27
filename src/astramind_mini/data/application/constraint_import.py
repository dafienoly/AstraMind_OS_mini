"""Resumable WP-0002B-H2 import and snapshot publication."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

import duckdb

from astramind_mini.contracts import DataSnapshot

from ..contracts import DatasetManifest
from ..ports import (
    AnnualConstraintCompactor,
    DataArtifactLedger,
    FileDatasetStore,
    HistoricalMarketDataProvider,
    LegacyMarketRelease,
    ParquetEncoder,
    RawRecordStore,
    ReleasableSnapshotStore,
)
from .constraint_publication import build_constraint_manifests
from .constraint_supplements import ConstraintSupplementService
from .constraint_validation import constraint_cross_coverage
from .datasets import DataSnapshotBuilder
from .identity import content_hash, file_hash
from .state_files import (
    constraint_year_is_intact,
    load_state,
    save_state,
)


@dataclass(frozen=True, slots=True)
class ConstraintImportPublication:
    snapshot: DataSnapshot
    manifests: tuple[DatasetManifest, ...]
    fetched: tuple[tuple[str, date], ...]


class ConstraintImportService:
    def __init__(
        self,
        *,
        data_root: Path,
        provider: HistoricalMarketDataProvider,
        raw_store: RawRecordStore,
        dataset_store: FileDatasetStore,
        snapshot_store: ReleasableSnapshotStore,
        ledger: DataArtifactLedger,
        compactor: AnnualConstraintCompactor,
        encoder: ParquetEncoder,
    ) -> None:
        self._root = data_root
        self._dataset_store = dataset_store
        self._snapshot_store = snapshot_store
        self._ledger = ledger
        self._compactor = compactor
        self._supplements = ConstraintSupplementService(
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
        republish: bool = False,
    ) -> ConstraintImportPublication:
        base = self._manifests(self._snapshot_store.get(base_snapshot_id))
        end_date = base["daily_market"].date_range[1]
        expected = self._expected_dates(base["trade_calendar"], start_date, end_date)
        price_start = min(_parse_dates(release.dates("stk_limit")))
        price_dates = frozenset(day for day in expected if day >= price_start)
        import_id = content_hash(
            {
                "base_snapshot_id": base_snapshot_id,
                "legacy_release": release.release_content_hash,
                "start_date": start_date,
                "end_date": end_date,
                "policy": "wp-0002b-h2-v1",
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
        if (snapshot_id := state.get("snapshot_id")) and not republish:
            return self._completed(str(snapshot_id), state)
        missing = {
            "daily_basic": expected - _parse_dates(release.dates("daily_basic")),
            "stk_limit": price_dates - _parse_dates(release.dates("stk_limit")),
            "suspend_d": expected - _parse_dates(release.dates("suspend_d")),
        }
        await self._supplements.prepare(
            staging=staging,
            state=state,
            state_path=state_path,
            missing=missing,
        )
        yearly = self._compact_years(
            release=release,
            expected=expected,
            price_dates=price_dates,
            staging=staging,
            state=state,
            state_path=state_path,
        )
        return self._publish(
            release=release,
            base=base,
            import_id=import_id,
            expected=expected,
            price_dates=price_dates,
            yearly=yearly,
            staging=staging,
            state=state,
            state_path=state_path,
        )

    def _compact_years(
        self,
        *,
        release: LegacyMarketRelease,
        expected: frozenset[date],
        price_dates: frozenset[date],
        staging: Path,
        state: dict[str, object],
        state_path: Path,
    ) -> dict[int, dict[str, object]]:
        completed = state["completed_years"]
        supplements = state["supplements"]
        assert isinstance(completed, dict)
        assert isinstance(supplements, dict)
        imported_at = datetime.fromisoformat(str(state["imported_at"]))
        for year in sorted({day.year for day in expected}):
            require_price = any(day.year == year for day in price_dates)
            existing = completed.get(str(year))
            if isinstance(existing, dict) and constraint_year_is_intact(
                existing, require_price_limit=require_price
            ):
                continue
            item = self._compact_year(
                release,
                year,
                require_price,
                staging,
                supplements,
                imported_at,
            )
            item["sessions"] = sum(day.year == year for day in expected)
            item["price_limit_sessions"] = sum(day.year == year for day in price_dates)
            completed[str(year)] = item
            save_state(state_path, state)
        return {int(year): value for year, value in completed.items() if isinstance(value, dict)}

    def _compact_year(
        self,
        release: LegacyMarketRelease,
        year: int,
        require_price: bool,
        staging: Path,
        supplements: dict[str, object],
        imported_at: datetime,
    ) -> dict[str, object]:
        item: dict[str, object] = {}
        specs = [
            ("daily_basic", "daily_basic"),
            ("suspend_d", "suspension_event"),
        ]
        if require_price:
            specs.append(("stk_limit", "price_limit"))
        for table, dataset in specs:
            output = staging / "annual" / dataset / f"{dataset.replace('_', '-')}-{year}.parquet"
            rows, _ = self._compactor.compact(
                table=table,
                source_files=release.files_for_year(table, year),
                supplement_files=_supplement_paths(supplements, table, year),
                output=output,
                imported_at=imported_at,
            )
            stats = self._compactor.validate(table, output)
            item[f"{dataset}_path"] = str(output)
            item[f"{dataset}_hash"] = file_hash(output)
            item[f"{dataset}_rows"] = rows
            item.update(stats)
        return item

    def _publish(
        self,
        *,
        release: LegacyMarketRelease,
        base: dict[str, DatasetManifest],
        import_id: str,
        expected: frozenset[date],
        price_dates: frozenset[date],
        yearly: dict[int, dict[str, object]],
        staging: Path,
        state: dict[str, object],
        state_path: Path,
    ) -> ConstraintImportPublication:
        finished_at = datetime.now(UTC)
        cross_coverage = constraint_cross_coverage(
            data_root=self._root,
            base=base,
            yearly=yearly,
            price_start=min(price_dates),
        )
        manifests, artifacts = build_constraint_manifests(
            base=base,
            release=release,
            import_id=import_id,
            expected_dates=expected,
            price_limit_dates=price_dates,
            yearly=yearly,
            cross_coverage=cross_coverage,
            staging=staging,
            finished_at=finished_at,
        )
        for manifest in manifests:
            path = self._dataset_store.publish_files(
                manifest,
                artifacts[manifest.dataset_name],
            )
            self._ledger.record_dataset(manifest, path)
        snapshot = DataSnapshotBuilder().build(
            manifests=(*base.values(), *manifests),
            as_of=finished_at,
            created_at=finished_at,
            code_identity="wp-0002b-h2-v1",
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
        return ConstraintImportPublication(snapshot, manifests, _fetched(state))

    def _completed(
        self,
        snapshot_id: str,
        state: dict[str, object],
    ) -> ConstraintImportPublication:
        snapshot = self._snapshot_store.get(snapshot_id)
        manifests = self._manifests(snapshot)
        selected = tuple(
            manifests[name] for name in ("daily_basic", "price_limit", "suspension_event")
        )
        return ConstraintImportPublication(snapshot, selected, _fetched(state))

    def _manifests(self, snapshot: DataSnapshot) -> dict[str, DatasetManifest]:
        result = {}
        for reference in snapshot.datasets:
            digest = reference.dataset_version.rsplit(":", 1)[-1]
            path = self._root / "datasets" / reference.dataset_name / digest / "manifest.json"
            result[reference.dataset_name] = DatasetManifest.model_validate_json(
                path.read_text(encoding="utf-8")
            )
        return result

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
                SELECT DISTINCT calendar_date FROM read_parquet(?)
                WHERE is_open AND calendar_date BETWEEN ? AND ?
                """,
                [str(path), start_date, end_date],
            ).fetchall()
        return frozenset(row[0] for row in rows)


def _parse_dates(values: frozenset[str]) -> frozenset[date]:
    return frozenset(date.fromisoformat(value) for value in values)


def _supplement_paths(
    supplements: dict[str, object],
    table: str,
    year: int,
) -> tuple[Path, ...]:
    table_state = supplements.get(table, {})
    if not isinstance(table_state, dict):
        raise ValueError("补充状态格式无效")
    paths = []
    for day, raw in table_state.items():
        if date.fromisoformat(day).year == year and isinstance(raw, dict):
            paths.append(Path(str(raw["path"])))
    return tuple(sorted(paths))


def _fetched(state: dict[str, object]) -> tuple[tuple[str, date], ...]:
    supplements = state.get("supplements", {})
    if not isinstance(supplements, dict):
        raise ValueError("补充状态格式无效")
    values: list[tuple[str, date]] = []
    for table, raw in supplements.items():
        if isinstance(raw, dict):
            values.extend((table, date.fromisoformat(day)) for day in raw)
    return tuple(sorted(values))


__all__ = ["ConstraintImportPublication", "ConstraintImportService"]
