"""Publish merged daily datasets before the atomic snapshot pointer switch."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from ..adapters import FilesystemDatasetStore
from ..contracts import DatasetManifest
from ..ports import DataArtifactLedger
from .daily_event_inputs import DailyEventInputs
from .daily_pipeline_inputs import (
    DailyDatasetExtensions,
    DailyPreparedInputs,
    PublishedDailyDatasets,
)
from .daily_pipeline_support import (
    daily_broad_index_manifest,
    daily_calendar_manifest,
    daily_industry_manifest,
    merge_broad_index_daily,
    merge_industry_daily,
)
from .daily_reference_inputs import DailyReferenceInputs
from .daily_research_inputs import artifact_sources
from .identity import file_hash


def publish_daily_datasets(
    *,
    data_root: Path,
    datasets: FilesystemDatasetStore,
    ledger: DataArtifactLedger,
    manifests: dict[str, DatasetManifest],
    paths: dict[str, tuple[Path, ...]],
    increments: tuple[Path, ...],
    broad_increment: Path | None,
    expected_l1: int,
    expected_l2: int,
    run_id: str,
    target_date: date,
    retrieved_at: datetime,
    workspace: Path,
    merged_calendar: Path,
    calendar_stats: tuple[int, date, date],
    prepared: DailyPreparedInputs,
    extensions: DailyDatasetExtensions | None,
) -> PublishedDailyDatasets:
    broad_index = None
    broad_index_path = None
    if broad_increment is not None:
        broad_merged = workspace / "broad_index_daily.parquet"
        broad_stats = merge_broad_index_daily(
            base_paths=paths["broad_index_daily"],
            increment=broad_increment,
            target_date=target_date,
            output=broad_merged,
        )
        broad_index = daily_broad_index_manifest(
            path=broad_merged,
            run_id=run_id,
            retrieved_at=retrieved_at,
            row_count=broad_stats[0],
            date_range=(broad_stats[1], broad_stats[2]),
        )
        broad_index_path = datasets.publish_files(
            broad_index,
            {"broad_index_daily.parquet": (broad_merged, file_hash(broad_merged))},
        )
        ledger.record_dataset(broad_index, broad_index_path)
    merged = workspace / "industry_index_daily.parquet"
    row_count, start_date, end_date = merge_industry_daily(
        base_paths=paths["industry_index_daily"],
        increments=increments,
        target_date=target_date,
        output=merged,
        expected_l1=expected_l1,
        expected_l2=expected_l2,
    )
    industry = daily_industry_manifest(
        path=merged,
        run_id=run_id,
        retrieved_at=retrieved_at,
        row_count=row_count,
        date_range=(start_date, end_date),
    )
    industry_path = datasets.publish_files(
        industry,
        {"industry_index_daily.parquet": (merged, file_hash(merged))},
    )
    ledger.record_dataset(industry, industry_path)
    calendar = daily_calendar_manifest(
        path=merged_calendar,
        run_id=run_id,
        retrieved_at=retrieved_at,
        row_count=calendar_stats[0],
        date_range=(calendar_stats[1], calendar_stats[2]),
    )
    calendar_path = datasets.publish_files(
        calendar,
        {"trade_calendar.parquet": (merged_calendar, file_hash(merged_calendar))},
    )
    ledger.record_dataset(calendar, calendar_path)
    research_paths = _publish_research(data_root, datasets, ledger, manifests, prepared)
    event_paths = _publish_direct(datasets, ledger, prepared.events)
    reference_paths = _publish_direct(datasets, ledger, prepared.references)
    return PublishedDailyDatasets(
        broad_index=broad_index,
        broad_index_path=broad_index_path,
        industry=industry,
        industry_path=industry_path,
        calendar=calendar,
        calendar_path=calendar_path,
        research=prepared.research,
        research_paths=research_paths,
        events=prepared.events.manifests if prepared.events is not None else {},
        event_paths=event_paths,
        references=prepared.references.manifests if prepared.references is not None else {},
        reference_paths=reference_paths,
        extensions=extensions.manifests if extensions is not None else {},
        extension_paths=extensions.paths if extensions is not None else {},
        extension_known_gaps=extensions.known_gaps if extensions is not None else (),
        extension_resolved_gaps=extensions.resolved_gaps if extensions is not None else (),
    )


def _publish_research(
    root: Path,
    datasets: FilesystemDatasetStore,
    ledger: DataArtifactLedger,
    manifests: dict[str, DatasetManifest],
    prepared: DailyPreparedInputs,
) -> dict[str, Path]:
    paths = {}
    for name, manifest in prepared.research.items():
        path = datasets.publish_files(
            manifest,
            artifact_sources(root, manifests[name], manifest, prepared.replacements[name]),
        )
        ledger.record_dataset(manifest, path)
        paths[name] = path
    return paths


def _publish_direct(
    datasets: FilesystemDatasetStore,
    ledger: DataArtifactLedger,
    prepared: DailyEventInputs | DailyReferenceInputs | None,
) -> dict[str, Path]:
    if prepared is None:
        return {}
    paths = {}
    for name, manifest in prepared.manifests.items():
        path = datasets.publish_files(manifest, prepared.artifacts[name])
        ledger.record_dataset(manifest, path)
        paths[name] = path
    return paths


__all__ = ["publish_daily_datasets"]
