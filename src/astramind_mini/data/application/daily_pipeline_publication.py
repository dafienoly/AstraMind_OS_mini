"""Final atomic snapshot, rotation and commit publication for WP-0025."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

from astramind_mini.contracts import DataSnapshot
from astramind_mini.market_regime.public import (
    FilesystemRotationStore,
    MarketRotationService,
    SnapshotRotationInput,
)

from ..adapters import (
    DailyPipelineStore,
    FilesystemDatasetStore,
    FilesystemSnapshotStore,
)
from ..contracts import DailyPipelineCommit, DailyPipelineStatus, DatasetManifest
from ..ports import DataArtifactLedger
from .daily_pipeline_identity import POLICY_VERSION, build_commit, replace_status
from .daily_pipeline_inputs import PublishedDailyDatasets
from .datasets import DataSnapshotBuilder

SHANGHAI = ZoneInfo("Asia/Shanghai")
Checkpoint = Callable[[str, str, datetime, str], None]
Interrupt = Callable[[str | None, str], None]


class DailyOutputPublisher:
    def __init__(
        self,
        *,
        data_root: Path,
        datasets: FilesystemDatasetStore,
        snapshots: FilesystemSnapshotStore,
        rotations: FilesystemRotationStore,
        control: DailyPipelineStore,
        ledger: DataArtifactLedger,
        checkpoint: Checkpoint,
        interrupt: Interrupt,
    ) -> None:
        self.data_root, self.datasets, self.snapshots = data_root, datasets, snapshots
        self.rotations, self.control, self.ledger = rotations, control, ledger
        self.checkpoint, self.interrupt = checkpoint, interrupt

    def publish(
        self,
        *,
        base: DataSnapshot,
        manifests: dict[str, DatasetManifest],
        published: PublishedDailyDatasets,
        run_id: str,
        target_date: date,
        retrieved_at: datetime,
        observed_l1: int,
        observed_l2: int,
        status: DailyPipelineStatus,
        interrupt_after_step: str | None,
    ) -> tuple[DailyPipelineStatus, DailyPipelineCommit]:
        return _publish(
            data_root=self.data_root,
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
            datasets=self.datasets,
            snapshots=self.snapshots,
            rotations=self.rotations,
            control=self.control,
            ledger=self.ledger,
            checkpoint=self.checkpoint,
            interrupt=self.interrupt,
        )


def _publish(
    *,
    data_root: Path,
    base: DataSnapshot,
    manifests: dict[str, DatasetManifest],
    published: PublishedDailyDatasets,
    run_id: str,
    target_date: date,
    retrieved_at: datetime,
    observed_l1: int,
    observed_l2: int,
    status: DailyPipelineStatus,
    interrupt_after_step: str | None,
    datasets: FilesystemDatasetStore,
    snapshots: FilesystemSnapshotStore,
    rotations: FilesystemRotationStore,
    control: DailyPipelineStore,
    ledger: DataArtifactLedger,
    checkpoint: Checkpoint,
    interrupt: Interrupt,
) -> tuple[DailyPipelineStatus, DailyPipelineCommit]:
    updated = {
        **manifests,
        "industry_index_daily": published.industry,
        "trade_calendar": published.calendar,
        **published.research,
        **published.events,
        **published.references,
        **published.extensions,
    }
    if published.broad_index is not None:
        updated["broad_index_daily"] = published.broad_index
    complete_at = max(
        base.as_of,
        retrieved_at,
        datetime.combine(target_date, time(18), tzinfo=SHANGHAI),
    )
    snapshot = DataSnapshotBuilder().build(
        manifests=tuple(updated.values()),
        as_of=complete_at,
        created_at=complete_at,
        code_identity=POLICY_VERSION,
        known_gaps=(*base.known_gaps, *published.extension_known_gaps),
        resolved_gaps=(
            *_resolved_reference_gaps(published),
            *published.extension_resolved_gaps,
        ),
    )
    snapshot_path = snapshots.publish(snapshot)
    ledger.record_snapshot(snapshot, snapshot_path)
    checkpoint(run_id, "snapshot", complete_at, snapshot.snapshot_id)
    interrupt(interrupt_after_step, "snapshot")
    rotation = MarketRotationService(
        source=SnapshotRotationInput(data_root),
        store=rotations,
    ).build(snapshot.snapshot_id)
    rotation_path = rotations.stage(rotation)
    checkpoint(run_id, "rotation", complete_at, rotation.rotation_snapshot_id)
    interrupt(interrupt_after_step, "rotation")
    _activate_datasets(published, datasets)
    snapshots.activate(
        snapshot,
        snapshot_path,
        expected_snapshot_id=base.snapshot_id,
    )
    rotations.activate(rotation, rotation_path)
    commit = build_commit(
        run_id,
        target_date,
        snapshot.snapshot_id,
        rotation.rotation_snapshot_id,
        complete_at,
    )
    control.commit(commit)
    checkpoint(run_id, "commit", complete_at, commit.commit_id)
    interrupt(interrupt_after_step, "commit")
    completed = replace_status(
        status,
        state="current",
        current_step=None,
        updated_at=complete_at,
        completed_at=complete_at,
        observed_l1_count=observed_l1,
        observed_l2_count=observed_l2,
        data_snapshot_id=snapshot.snapshot_id,
        rotation_snapshot_id=rotation.rotation_snapshot_id,
    )
    control.publish_status(completed)
    return completed, commit


def _activate_datasets(
    published: PublishedDailyDatasets,
    datasets: FilesystemDatasetStore,
) -> None:
    if published.broad_index is not None and published.broad_index_path is not None:
        datasets.activate(published.broad_index, published.broad_index_path)
    datasets.activate(published.industry, published.industry_path)
    datasets.activate(published.calendar, published.calendar_path)
    groups = (
        (published.research, published.research_paths),
        (published.events, published.event_paths),
        (published.references, published.reference_paths),
        (published.extensions, published.extension_paths),
    )
    for manifests, paths in groups:
        for name, manifest in manifests.items():
            datasets.activate(manifest, paths[name])


def _resolved_reference_gaps(
    published: PublishedDailyDatasets,
) -> tuple[str, ...]:
    if not published.references:
        return ()
    return (
        "current_name_history_not_available",
        "current_security_master_not_available",
        "current_corporate_action_not_available",
        "current_industry_taxonomy_not_available",
        "current_industry_membership_not_available",
    )


__all__ = ["DailyOutputPublisher"]
