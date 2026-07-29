"""Deterministic run, status and commit identities for WP-0025."""

from __future__ import annotations

from datetime import date, datetime
from typing import Protocol

from ..contracts import DailyPipelineCheckpoint, DailyPipelineCommit, DailyPipelineStatus
from .identity import content_hash

POLICY_VERSION = "wp-0025-daily-reference-v1.3.0"


class CheckpointStore(Protocol):
    def publish_checkpoint(self, value: DailyPipelineCheckpoint) -> None: ...


def build_run_id(base_snapshot_id: str, target_date: date) -> str:
    digest = content_hash(
        {
            "base_snapshot_id": base_snapshot_id,
            "target_date": target_date,
            "policy_version": POLICY_VERSION,
        }
    )
    return "daily-pipeline:" + digest.removeprefix("sha256:")


def build_status(**values: object) -> DailyPipelineStatus:
    identity = {**values, "broker_actions_allowed": False}
    return DailyPipelineStatus.model_validate({**identity, "content_hash": content_hash(identity)})


def replace_status(value: DailyPipelineStatus, **changes: object) -> DailyPipelineStatus:
    identity = value.model_dump(exclude={"content_hash"})
    identity.update(changes)
    return DailyPipelineStatus.model_validate({**identity, "content_hash": content_hash(identity)})


def touch_status(value: DailyPipelineStatus, updated_at: datetime) -> DailyPipelineStatus:
    return replace_status(value, updated_at=max(value.updated_at, updated_at))


def build_commit(
    run_id: str,
    target_date: date,
    snapshot_id: str,
    rotation_id: str,
    committed_at: datetime,
) -> DailyPipelineCommit:
    identity = {
        "run_id": run_id,
        "target_date": target_date,
        "data_snapshot_id": snapshot_id,
        "rotation_snapshot_id": rotation_id,
        "committed_at": committed_at,
        "broker_actions_allowed": False,
    }
    digest = content_hash(identity)
    return DailyPipelineCommit(
        commit_id="daily-pipeline-commit:" + digest.removeprefix("sha256:"),
        run_id=run_id,
        target_date=target_date,
        data_snapshot_id=snapshot_id,
        rotation_snapshot_id=rotation_id,
        committed_at=committed_at,
        broker_actions_allowed=False,
        content_hash=digest,
    )


def publish_checkpoint(
    store: CheckpointStore,
    run_id: str,
    step_id: str,
    completed_at: datetime,
    artifact: str,
) -> None:
    identity = {
        "run_id": run_id,
        "step_id": step_id,
        "artifact_identity": artifact,
        "completed_at": completed_at,
    }
    store.publish_checkpoint(
        DailyPipelineCheckpoint(
            run_id=run_id,
            step_id=step_id,
            artifact_identity=artifact,
            completed_at=completed_at,
            content_hash=content_hash(identity),
        )
    )


__all__ = [
    "POLICY_VERSION",
    "build_commit",
    "build_run_id",
    "build_status",
    "publish_checkpoint",
    "replace_status",
    "touch_status",
]
