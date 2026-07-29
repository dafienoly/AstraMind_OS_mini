"""Resumable L1/L2 daily increment and atomic publication orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from astramind_mini.contracts import DataSnapshot
from astramind_mini.market_regime.public import FilesystemRotationStore

from ..adapters import (
    DailyPipelineStore,
    FilesystemDatasetStore,
    FilesystemRawRecordStore,
    FilesystemSnapshotStore,
)
from ..contracts import (
    DailyPipelineCommit,
    DailyPipelineStatus,
    DatasetManifest,
)
from ..ports import (
    DataArtifactLedger,
    HistoricalMarketDataProvider,
    ParquetEncoder,
)
from .daily_pipeline_collection import collect_calendar, collect_industries
from .daily_pipeline_identity import (
    POLICY_VERSION,
    build_run_id,
    build_status,
    publish_checkpoint,
    replace_status,
    touch_status,
)
from .daily_pipeline_inputs import (
    DailyPreparedInputs,
    PublishedDailyDatasets,
    prepare_daily_inputs,
    prepare_daily_reference_scope,
    waiting_provider_status,
    waiting_reason,
)
from .daily_pipeline_publication import DailyOutputPublisher
from .daily_pipeline_support import (
    daily_calendar_manifest,
    daily_industry_manifest,
    load_snapshot_bundle,
    merge_industry_daily,
    merge_trade_calendar,
    published_industries,
)
from .daily_reference_inputs import DailyReferenceInputs
from .daily_research_inputs import artifact_sources
from .identity import content_hash, file_hash
from .state_files import load_state


class DailyPipelineInterrupted(RuntimeError):
    """Synthetic interruption after a durable daily-pipeline checkpoint."""


@dataclass(frozen=True, slots=True)
class DailyPipelineResult:
    status: DailyPipelineStatus
    commit: DailyPipelineCommit | None


class DailyIndustryPipeline:
    def __init__(
        self,
        *,
        data_root: Path,
        rotation_root: Path,
        provider: HistoricalMarketDataProvider,
        encoder: ParquetEncoder,
        raw_store: FilesystemRawRecordStore,
        dataset_store: FilesystemDatasetStore,
        snapshot_store: FilesystemSnapshotStore,
        rotation_store: FilesystemRotationStore,
        control_store: DailyPipelineStore,
        ledger: DataArtifactLedger,
    ) -> None:
        self._root = data_root
        self._provider = provider
        self._encoder = encoder
        self._raw = raw_store
        self._datasets = dataset_store
        self._snapshots = snapshot_store
        self._rotations = rotation_store
        self._control = control_store
        self._ledger = ledger
        self._publisher = DailyOutputPublisher(
            data_root=data_root,
            datasets=dataset_store,
            snapshots=snapshot_store,
            rotations=rotation_store,
            control=control_store,
            ledger=ledger,
            checkpoint=self._checkpoint,
            interrupt=self._interrupt,
        )

    async def run(
        self,
        *,
        base_snapshot_id: str,
        target_date: date,
        started_at: datetime,
        interrupt_after_step: str | None = None,
        include_research_inputs: bool = True,
        include_event_inputs: bool = True,
    ) -> DailyPipelineResult:
        if started_at.tzinfo is None:
            raise ValueError("日度管线启动时间必须带时区")
        self._control.migrate()
        try:
            current_commit = self._control.current_commit()
        except FileNotFoundError:
            current_commit = None
        if (
            current_commit is not None
            and current_commit.target_date == target_date
            and self._snapshots.get(current_commit.data_snapshot_id).code_identity == POLICY_VERSION
        ):
            current_status = self._control.status(current_commit.run_id)
            if current_status is None or current_status.state != "current":
                raise ValueError("日度提交指针缺少一致的完成状态")
            current_status = touch_status(current_status, started_at)
            self._control.publish_status(current_status)
            return DailyPipelineResult(current_status, current_commit)
        requested_run_id = build_run_id(base_snapshot_id, target_date)
        base, manifests, paths = load_snapshot_bundle(self._root, base_snapshot_id)
        industries = published_industries(paths["industry_taxonomy"])
        expected_l1 = sum(level == "L1" for level, _, _ in industries)
        expected_l2 = sum(level == "L2" for level, _, _ in industries)
        run_id = requested_run_id
        existing = self._control.status(run_id)
        if existing and existing.state == "current":
            commit = self._control.current_commit()
            if commit.run_id != run_id:
                raise ValueError("日度运行已完成但当前提交指针不一致")
            return DailyPipelineResult(existing, commit)
        workspace = self._root / "daily-runs" / run_id.rsplit(":", 1)[-1]
        state_path = workspace / "requests.json"
        state = load_state(state_path) or {"calendar": None, "industries": {}}
        status = build_status(
            run_id=run_id,
            target_date=target_date,
            base_snapshot_id=base_snapshot_id,
            state="running",
            current_step="provider_collect",
            attempt=(existing.attempt + 1) if existing else 1,
            expected_l1_count=expected_l1,
            expected_l2_count=expected_l2,
            started_at=existing.started_at if existing else started_at,
            updated_at=started_at,
        )
        self._control.publish_status(status)
        try:
            return await self._execute(
                base=base,
                manifests=manifests,
                paths=paths,
                industries=industries,
                expected_l1=expected_l1,
                expected_l2=expected_l2,
                run_id=run_id,
                workspace=workspace,
                state_path=state_path,
                state=state,
                status=status,
                target_date=target_date,
                started_at=started_at,
                interrupt_after_step=interrupt_after_step,
                include_research_inputs=include_research_inputs,
                include_event_inputs=include_event_inputs,
            )
        except DailyPipelineInterrupted:
            interrupted = replace_status(
                status,
                state="recovery_required",
                updated_at=started_at,
                blocker_codes=("pipeline_interrupted",),
                recovery_action="以相同基础快照和目标日期重新运行",
            )
            self._control.publish_status(interrupted)
            raise
        except Exception:
            blocked = replace_status(
                status,
                state="blocked",
                updated_at=started_at,
                blocker_codes=("daily_pipeline_failed",),
                recovery_action="检查脱敏错误后从最后完整检查点恢复",
            )
            self._control.publish_status(blocked)
            raise

    async def _execute(
        self,
        *,
        base: DataSnapshot,
        manifests: dict[str, DatasetManifest],
        paths: dict[str, tuple[Path, ...]],
        industries: tuple[tuple[str, str, str], ...],
        expected_l1: int,
        expected_l2: int,
        run_id: str,
        workspace: Path,
        state_path: Path,
        state: dict[str, object],
        status: DailyPipelineStatus,
        target_date: date,
        started_at: datetime,
        interrupt_after_step: str | None,
        include_research_inputs: bool,
        include_event_inputs: bool,
    ) -> DailyPipelineResult:
        calendar_open, calendar_increment, calendar_received = await collect_calendar(
            state=state,
            state_path=state_path,
            workspace=workspace,
            target_date=target_date,
            provider=self._provider,
            encoder=self._encoder,
            raw_store=self._raw,
        )
        if not calendar_open:
            result = replace_status(status, state="no_session", updated_at=started_at)
            self._control.publish_status(result)
            return DailyPipelineResult(result, None)
        references = None
        if include_research_inputs:
            references, industries, expected_l1, expected_l2 = await prepare_daily_reference_scope(
                root=self._root,
                provider=self._provider,
                raw_store=self._raw,
                encoder=self._encoder,
                manifests=manifests,
                paths=paths,
                workspace=workspace,
                state=state,
                state_path=state_path,
                run_id=run_id,
                target_date=target_date,
            )
            status = replace_status(
                status,
                expected_l1_count=expected_l1,
                expected_l2_count=expected_l2,
                updated_at=references.retrieved_at,
            )
            self._control.publish_status(status)
        increments, retrieved_at, observed_l1, observed_l2 = await collect_industries(
            state=state,
            state_path=state_path,
            workspace=workspace,
            industries=industries,
            target_date=target_date,
            provider=self._provider,
            encoder=self._encoder,
            raw_store=self._raw,
        )
        retrieved_at = max(retrieved_at, calendar_received)
        reason = waiting_reason(
            expected=(expected_l1, expected_l2),
            observed=(observed_l1, observed_l2),
            root=self._root,
            manifests=manifests,
            started_at=started_at,
            target_date=target_date,
            include_events=include_event_inputs,
        )
        if reason is not None:
            waiting = waiting_provider_status(
                status,
                updated_at=retrieved_at,
                observed_l1=observed_l1,
                observed_l2=observed_l2,
                reason=reason,
            )
            self._control.publish_status(waiting)
            return DailyPipelineResult(waiting, None)
        return await self._publish_ready(
            base=base,
            manifests=manifests,
            paths=paths,
            calendar_increment=calendar_increment,
            increments=increments,
            expected_l1=expected_l1,
            expected_l2=expected_l2,
            run_id=run_id,
            target_date=target_date,
            retrieved_at=retrieved_at,
            workspace=workspace,
            state=state,
            state_path=state_path,
            status=status,
            observed_l1=observed_l1,
            observed_l2=observed_l2,
            interrupt_after_step=interrupt_after_step,
            include_research_inputs=include_research_inputs,
            include_event_inputs=include_event_inputs,
            references=references,
        )

    async def _publish_ready(
        self,
        *,
        base: DataSnapshot,
        manifests: dict[str, DatasetManifest],
        paths: dict[str, tuple[Path, ...]],
        calendar_increment: Path,
        increments: tuple[Path, ...],
        expected_l1: int,
        expected_l2: int,
        run_id: str,
        target_date: date,
        retrieved_at: datetime,
        workspace: Path,
        state: dict[str, object],
        state_path: Path,
        status: DailyPipelineStatus,
        observed_l1: int,
        observed_l2: int,
        interrupt_after_step: str | None,
        include_research_inputs: bool,
        include_event_inputs: bool,
        references: DailyReferenceInputs | None,
    ) -> DailyPipelineResult:
        merged_calendar = workspace / "trade_calendar.parquet"
        calendar_stats = merge_trade_calendar(
            base_paths=paths["trade_calendar"],
            increment=calendar_increment,
            replace_from=target_date,
            output=merged_calendar,
        )
        prepared = await prepare_daily_inputs(
            root=self._root,
            provider=self._provider,
            raw_store=self._raw,
            encoder=self._encoder,
            manifests=manifests,
            paths=paths,
            workspace=workspace,
            state=state,
            state_path=state_path,
            calendar_path=merged_calendar,
            run_id=run_id,
            target_date=target_date,
            retrieved_at=retrieved_at,
            include_research=include_research_inputs,
            include_events=include_event_inputs,
            references=references,
        )
        retrieved_at = prepared.retrieved_at
        self._checkpoint(run_id, "provider_collect", retrieved_at, content_hash(state))
        self._interrupt(interrupt_after_step, "provider_collect")
        published = self._publish_datasets(
            manifests=manifests,
            paths=paths,
            increments=increments,
            expected_l1=expected_l1,
            expected_l2=expected_l2,
            run_id=run_id,
            target_date=target_date,
            retrieved_at=retrieved_at,
            workspace=workspace,
            merged_calendar=merged_calendar,
            calendar_stats=calendar_stats,
            prepared=prepared,
        )
        self._checkpoint(run_id, "dataset", retrieved_at, published.industry.dataset_version)
        self._interrupt(interrupt_after_step, "dataset")
        completed, commit = self._publisher.publish(
            base=base,
            manifests=manifests,
            published=published,
            run_id=run_id,
            target_date=target_date,
            retrieved_at=retrieved_at,
            observed_l1=observed_l1,
            observed_l2=observed_l2,
            status=status,
            interrupt_after_step=interrupt_after_step,
        )
        return DailyPipelineResult(completed, commit)

    def _publish_datasets(
        self,
        *,
        manifests: dict[str, DatasetManifest],
        paths: dict[str, tuple[Path, ...]],
        increments: tuple[Path, ...],
        expected_l1: int,
        expected_l2: int,
        run_id: str,
        target_date: date,
        retrieved_at: datetime,
        workspace: Path,
        merged_calendar: Path,
        calendar_stats: tuple[int, date, date],
        prepared: DailyPreparedInputs,
    ) -> PublishedDailyDatasets:
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
        industry_path = self._datasets.publish_files(
            industry,
            {"industry_index_daily.parquet": (merged, file_hash(merged))},
        )
        self._ledger.record_dataset(industry, industry_path)
        calendar = daily_calendar_manifest(
            path=merged_calendar,
            run_id=run_id,
            retrieved_at=retrieved_at,
            row_count=calendar_stats[0],
            date_range=(calendar_stats[1], calendar_stats[2]),
        )
        calendar_path = self._datasets.publish_files(
            calendar,
            {"trade_calendar.parquet": (merged_calendar, file_hash(merged_calendar))},
        )
        self._ledger.record_dataset(calendar, calendar_path)
        research_paths: dict[str, Path] = {}
        for name, manifest in prepared.research.items():
            path = self._datasets.publish_files(
                manifest,
                artifact_sources(
                    self._root,
                    manifests[name],
                    manifest,
                    prepared.replacements[name],
                ),
            )
            self._ledger.record_dataset(manifest, path)
            research_paths[name] = path
        event_paths: dict[str, Path] = {}
        if prepared.events is not None:
            for name, manifest in prepared.events.manifests.items():
                path = self._datasets.publish_files(
                    manifest,
                    prepared.events.artifacts[name],
                )
                self._ledger.record_dataset(manifest, path)
                event_paths[name] = path
        reference_paths: dict[str, Path] = {}
        if prepared.references is not None:
            for name, manifest in prepared.references.manifests.items():
                path = self._datasets.publish_files(
                    manifest,
                    prepared.references.artifacts[name],
                )
                self._ledger.record_dataset(manifest, path)
                reference_paths[name] = path
        return PublishedDailyDatasets(
            industry,
            industry_path,
            calendar,
            calendar_path,
            prepared.research,
            research_paths,
            prepared.events.manifests if prepared.events is not None else {},
            event_paths,
            prepared.references.manifests if prepared.references is not None else {},
            reference_paths,
        )

    def _checkpoint(self, run_id: str, step_id: str, completed_at: datetime, artifact: str) -> None:
        publish_checkpoint(self._control, run_id, step_id, completed_at, artifact)

    @staticmethod
    def _interrupt(requested: str | None, step: str) -> None:
        if requested == step:
            raise DailyPipelineInterrupted(f"在 {step} 检查点后模拟中断")


__all__ = [
    "POLICY_VERSION",
    "DailyIndustryPipeline",
    "DailyPipelineInterrupted",
    "DailyPipelineResult",
]
