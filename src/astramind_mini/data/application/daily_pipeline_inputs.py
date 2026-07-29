"""Bounded preparation of stock research and tactical-event daily inputs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

from ..contracts import DailyPipelineStatus, DatasetManifest
from ..ports import HistoricalMarketDataProvider, ParquetEncoder, RawRecordStore
from .daily_event_inputs import (
    DailyEventInputs,
    event_base_manifests,
    prepare_daily_event_inputs,
)
from .daily_pipeline_identity import replace_status
from .daily_pipeline_support import published_industries
from .daily_reference_inputs import (
    DailyReferenceInputs,
    prepare_daily_reference_inputs,
)
from .daily_research_inputs import publish_daily_research_inputs

SHANGHAI = ZoneInfo("Asia/Shanghai")


@dataclass(frozen=True, slots=True)
class DailyPreparedInputs:
    references: DailyReferenceInputs | None
    research: dict[str, DatasetManifest]
    replacements: dict[str, Path]
    events: DailyEventInputs | None
    retrieved_at: datetime


@dataclass(frozen=True, slots=True)
class DailyDatasetExtensions:
    manifests: dict[str, DatasetManifest]
    paths: dict[str, Path]
    retrieved_at: datetime
    known_gaps: tuple[str, ...] = ()
    resolved_gaps: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class PublishedDailyDatasets:
    broad_index: DatasetManifest | None
    broad_index_path: Path | None
    industry: DatasetManifest
    industry_path: Path
    calendar: DatasetManifest
    calendar_path: Path
    research: dict[str, DatasetManifest]
    research_paths: dict[str, Path]
    events: dict[str, DatasetManifest]
    event_paths: dict[str, Path]
    references: dict[str, DatasetManifest]
    reference_paths: dict[str, Path]
    extensions: dict[str, DatasetManifest]
    extension_paths: dict[str, Path]
    extension_known_gaps: tuple[str, ...]
    extension_resolved_gaps: tuple[str, ...]


def events_waiting(
    root: Path,
    manifests: dict[str, DatasetManifest],
    evaluated_at: datetime,
    target_date: date,
    enabled: bool,
) -> bool:
    if not enabled or not event_base_manifests(root, manifests):
        return False
    local_evaluated = evaluated_at.astimezone(SHANGHAI)
    return local_evaluated.date() == target_date and local_evaluated.time() < time(20, 5)


async def prepare_daily_reference_scope(
    *,
    root: Path,
    provider: HistoricalMarketDataProvider,
    raw_store: RawRecordStore,
    encoder: ParquetEncoder,
    manifests: dict[str, DatasetManifest],
    paths: dict[str, tuple[Path, ...]],
    workspace: Path,
    state: dict[str, object],
    state_path: Path,
    run_id: str,
    target_date: date,
) -> tuple[
    DailyReferenceInputs,
    tuple[tuple[str, str, str], ...],
    int,
    int,
]:
    references = await prepare_daily_reference_inputs(
        root=root,
        provider=provider,
        raw_store=raw_store,
        encoder=encoder,
        manifests=manifests,
        base_paths=paths,
        workspace=workspace,
        state=state,
        state_path=state_path,
        run_id=run_id,
        target_date=target_date,
    )
    industries = published_industries((references.paths["industry_taxonomy"],))
    return (
        references,
        industries,
        sum(level == "L1" for level, _, _ in industries),
        sum(level == "L2" for level, _, _ in industries),
    )


def waiting_reason(
    *,
    expected: tuple[int, int],
    observed: tuple[int, int],
    broad_index_count: int = 6,
    root: Path,
    manifests: dict[str, DatasetManifest],
    evaluated_at: datetime,
    target_date: date,
    include_events: bool,
    include_extensions: bool = False,
) -> Literal["broad_index", "industry", "events", "extensions"] | None:
    if broad_index_count != 6:
        return "broad_index"
    if observed != expected:
        return "industry"
    local_evaluated = evaluated_at.astimezone(SHANGHAI)
    if (
        include_extensions
        and local_evaluated.date() == target_date
        and local_evaluated.time() < time(18, 5)
    ):
        return "extensions"
    if events_waiting(root, manifests, evaluated_at, target_date, include_events):
        return "events"
    return None


def waiting_provider_status(
    status: DailyPipelineStatus,
    *,
    updated_at: datetime,
    observed_l1: int,
    observed_l2: int,
    reason: Literal["broad_index", "industry", "events", "extensions"],
) -> DailyPipelineStatus:
    blocker, action = {
        "broad_index": (
            "broad_index_daily_incomplete",
            "六个宽基指数数据完整后以相同目标日期重跑",
        ),
        "industry": (
            "industry_daily_incomplete",
            "提供方数据完整后以相同目标日期重跑",
        ),
        "events": (
            "event_publish_window_not_reached",
            "20:05 后以相同目标日期重跑事件增量",
        ),
        "extensions": (
            "etf_publish_window_not_reached",
            "18:05 后以相同目标日期重跑 ETF 日线增量",
        ),
    }[reason]
    return replace_status(
        status,
        state="waiting_provider",
        updated_at=updated_at,
        observed_l1_count=observed_l1,
        observed_l2_count=observed_l2,
        blocker_codes=(blocker,),
        recovery_action=action,
    )


async def prepare_daily_inputs(
    *,
    root: Path,
    provider: HistoricalMarketDataProvider,
    raw_store: RawRecordStore,
    encoder: ParquetEncoder,
    manifests: dict[str, DatasetManifest],
    paths: dict[str, tuple[Path, ...]],
    workspace: Path,
    state: dict[str, object],
    state_path: Path,
    calendar_path: Path,
    run_id: str,
    target_date: date,
    retrieved_at: datetime,
    include_research: bool,
    include_events: bool,
    references: DailyReferenceInputs | None = None,
) -> DailyPreparedInputs:
    research: dict[str, DatasetManifest] = {}
    replacements: dict[str, Path] = {}
    if include_research:
        research, replacements, retrieved_at = await publish_daily_research_inputs(
            root=root,
            provider=provider,
            raw_store=raw_store,
            encoder=encoder,
            manifests=manifests,
            paths=paths,
            workspace=workspace,
            calendar_path=calendar_path,
            run_id=run_id,
            target_date=target_date,
            retrieved_at=retrieved_at,
            reference_paths=references.paths if references is not None else None,
        )
    events = None
    if include_events:
        events = await prepare_daily_event_inputs(
            root=root,
            provider=provider,
            raw_store=raw_store,
            encoder=encoder,
            snapshot_manifests=manifests,
            workspace=workspace,
            state=state,
            state_path=state_path,
            target_date=target_date,
        )
        if events is not None:
            retrieved_at = max(retrieved_at, events.retrieved_at)
    if references is not None:
        retrieved_at = max(retrieved_at, references.retrieved_at)
    return DailyPreparedInputs(references, research, replacements, events, retrieved_at)


__all__ = [
    "DailyDatasetExtensions",
    "DailyPreparedInputs",
    "PublishedDailyDatasets",
    "events_waiting",
    "prepare_daily_inputs",
    "prepare_daily_reference_scope",
    "waiting_provider_status",
    "waiting_reason",
]
