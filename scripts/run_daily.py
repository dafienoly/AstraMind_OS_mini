"""Run, recover, or inspect the broker-free WP-0030 daily chain."""

from __future__ import annotations

import argparse
import asyncio
import fcntl
import json
import subprocess
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from typing import Literal

from astramind_mini.config import Settings
from astramind_mini.data.adapters import DailyPipelineStore
from astramind_mini.data.application.daily_pipeline_identity import build_run_id
from astramind_mini.local_ops.contracts import BackupManifest, DailyDecisionStatus
from astramind_mini.local_ops.daily_decision_store import DailyDecisionStore
from astramind_mini.local_ops.daily_run import (
    BackupReadinessOutcome,
    DailyDataOutcome,
    DailyDecisionOutcome,
    DailyRunOrchestrator,
)
from astramind_mini.local_ops.daily_run_store import (
    DailyRunLeaseUnavailable,
    DailyRunStore,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider-env-file", type=Path)
    parser.add_argument("--target-date", type=date.fromisoformat)
    parser.add_argument("--base-snapshot-id")
    parser.add_argument("--run-id")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--recover", action="store_true")
    return parser.parse_args()


async def run(args: argparse.Namespace) -> int:
    settings = Settings()
    store = DailyRunStore(settings.local_ops_db_path, Path("var/operations/daily-runs"))
    if args.status:
        status = store.status(args.run_id) if args.run_id else store.latest_status()
        if status is None:
            print("state=waiting_window")
            print("broker_actions_allowed=false")
            return 0
        _print_status(status.model_dump(mode="json"))
        return 0

    target_date, base_snapshot_id, rebuild_completed = _resolve_identity(args, store, settings)
    pipeline_run_id = build_run_id(base_snapshot_id, target_date)
    if args.provider_env_file is None:
        raise ValueError("运行或恢复日常任务必须提供 --provider-env-file")

    orchestrator = DailyRunOrchestrator(
        store=store,
        run_data=lambda: _run_data(
            settings=settings,
            provider_env_file=args.provider_env_file,
            target_date=target_date,
            base_snapshot_id=base_snapshot_id,
            force_rebuild=rebuild_completed,
        ),
        run_decision=lambda: _run_decision(settings, pipeline_run_id),
        check_backup=lambda: _check_backup(settings, target_date),
    )
    try:
        result = await orchestrator.run(
            target_date=target_date,
            base_snapshot_id=base_snapshot_id,
            recover=args.recover,
        )
    except DailyRunLeaseUnavailable:
        print("state=lease_held")
        print("recovery_action=查看现有运行 make daily-run-status")
        print("broker_actions_allowed=false")
        return 0
    _print_status(result.status.model_dump(mode="json"))
    if result.summary:
        print(f"summary_id={result.summary.summary_id}")
    if result.artifact_path:
        print(f"artifact_path={result.artifact_path}")
    return 0


def _resolve_identity(
    args: argparse.Namespace, store: DailyRunStore, settings: Settings
) -> tuple[date, str, bool]:
    if args.recover:
        if not args.run_id:
            raise ValueError("恢复必须提供 --run-id")
        status = store.status(args.run_id)
        if status is None:
            raise ValueError("待恢复的日常运行不存在")
        return status.target_date, status.base_snapshot_id, status.state == "current"
    if args.target_date is None:
        raise ValueError("运行日常任务必须提供 --target-date")
    return (
        args.target_date,
        args.base_snapshot_id or _current_snapshot_id(settings.data_dir),
        False,
    )


def _run_data(
    *,
    settings: Settings,
    provider_env_file: Path,
    target_date: date,
    base_snapshot_id: str,
    force_rebuild: bool,
) -> DailyDataOutcome:
    control = DailyPipelineStore(settings.control_db_path, settings.data_dir)
    pipeline_run_id = build_run_id(base_snapshot_id, target_date)
    existing = control.status(pipeline_run_id)
    command = [
        sys.executable,
        "scripts/run_daily_data_pipeline.py",
        "--provider-env-file",
        str(provider_env_file),
        "--target-date",
        target_date.isoformat(),
        "--base-snapshot-id",
        base_snapshot_id,
    ]
    if force_rebuild or (existing is not None and existing.state != "current"):
        command.append("--recover")
    completed = subprocess.run(command, check=False)
    status = control.status(pipeline_run_id)
    if status is None:
        return DailyDataOutcome(
            state="recovery_required",
            blocker_codes=("daily_pipeline_status_missing",),
            recovery_action="检查日度数据状态后恢复同一运行",
        )
    if completed.returncode != 0:
        return DailyDataOutcome(
            state="recovery_required",
            blocker_codes=("daily_pipeline_process_failed",),
            recovery_action="运行 make daily-data-status 后恢复",
        )
    if status.state != "current":
        state: Literal["waiting_provider", "stale", "blocked", "recovery_required"]
        if status.state in ("waiting_provider", "stale", "blocked", "recovery_required"):
            state = status.state
        else:
            state = "recovery_required"
        return DailyDataOutcome(
            state=state,
            blocker_codes=status.blocker_codes,
            recovery_action=status.recovery_action,
        )
    commit = control.commit_for_run(pipeline_run_id)
    if commit is None or commit.target_date != target_date:
        return DailyDataOutcome(
            state="blocked",
            blocker_codes=("daily_pipeline_identity_drift",),
            recovery_action="核对日度数据提交身份后恢复",
        )
    return DailyDataOutcome(
        state="completed",
        commit_id=commit.commit_id,
        data_snapshot_id=commit.data_snapshot_id,
        rotation_snapshot_id=commit.rotation_snapshot_id,
    )


def _run_decision(settings: Settings, pipeline_run_id: str) -> DailyDecisionOutcome:
    pipeline = DailyPipelineStore(settings.control_db_path, settings.data_dir)
    commit = pipeline.commit_for_run(pipeline_run_id)
    if commit is None:
        return DailyDecisionOutcome(
            state="recovery_required",
            blocker_codes=("daily_pipeline_commit_missing",),
            recovery_action="恢复准确日度数据提交后重跑决策链",
        )
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/run_daily_decision_chain.py",
            "--pipeline-run-id",
            pipeline_run_id,
        ],
        check=False,
    )
    store = DailyDecisionStore(
        settings.local_ops_db_path,
        Path("var/research/daily-decision"),
    )
    status: DailyDecisionStatus | None = store.latest_status_for_pipeline_commit(commit.commit_id)
    if completed.returncode != 0 or status is None:
        return DailyDecisionOutcome(
            state="recovery_required",
            blocker_codes=("daily_decision_process_failed",),
            recovery_action="运行 make daily-decision-status 后恢复",
        )
    if status.state != "current":
        decision_state: Literal["blocked", "recovery_required"] = (
            "recovery_required" if status.state == "recovery_required" else "blocked"
        )
        return DailyDecisionOutcome(
            state=decision_state,
            blocker_codes=status.blocker_codes,
            recovery_action=status.recovery_action,
        )
    return DailyDecisionOutcome(
        state="completed",
        feature_snapshot_id=status.feature_snapshot_id,
        prediction_batch_id=status.prediction_batch_id,
        portfolio_target_id=status.portfolio_target_id,
        order_plan_id=status.order_plan_id,
    )


def _check_backup(settings: Settings, target_date: date) -> BackupReadinessOutcome:
    if settings.backup_dir is None:
        return BackupReadinessOutcome(
            ready=False,
            blocker_codes=("backup_directory_not_configured",),
            recovery_action="配置 ASTRAMIND_BACKUP_DIR 并运行 make ops-backup",
        )
    latest = _latest_complete_backup(settings.backup_dir, target_date)
    if latest is None:
        completed = subprocess.run(
            [
                sys.executable,
                "scripts/backup_local_state.py",
                "--reason",
                "daily_close",
                "--logical-date",
                target_date.isoformat(),
            ],
            check=False,
        )
        if completed.returncode != 0:
            return BackupReadinessOutcome(
                ready=False,
                blocker_codes=("daily_backup_failed",),
                recovery_action="检查外部备份目录后运行 make ops-backup，再恢复日常运行",
            )
        latest = _latest_complete_backup(settings.backup_dir, target_date)
    if latest is None:
        return BackupReadinessOutcome(
            ready=False,
            blocker_codes=("daily_backup_not_ready",),
            recovery_action="运行 make ops-backup BACKUP_REASON=daily_close 后恢复",
        )
    return BackupReadinessOutcome(ready=True, backup_id=latest.backup_id)


def _latest_complete_backup(backup_root: Path, target_date: date) -> BackupManifest | None:
    manifests = []
    namespace = backup_root / "astramind-mini" / "daily"
    for path in namespace.glob("*/*/manifest.json"):
        try:
            manifest = BackupManifest.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if manifest.logical_date >= target_date and manifest.status == "complete":
            manifests.append(manifest)
    return (
        max(manifests, key=lambda item: (item.logical_date, item.created_at, item.backup_id))
        if manifests
        else None
    )


def _current_snapshot_id(root: Path) -> str:
    value = json.loads((root / "current" / "data-snapshot.json").read_text(encoding="utf-8"))
    snapshot_id = value.get("snapshot_id") if isinstance(value, dict) else None
    if not isinstance(snapshot_id, str):
        raise ValueError("当前 DataSnapshot 指针无效")
    return snapshot_id


def _print_status(value: dict[str, object]) -> None:
    for field in (
        "run_id",
        "state",
        "target_date",
        "current_step",
        "data_commit_id",
        "data_snapshot_id",
        "portfolio_target_id",
        "order_plan_id",
        "backup_id",
        "recovery_action",
    ):
        if value.get(field) is not None:
            print(f"{field}={value[field]}")
    blockers = value.get("blocker_codes")
    values = tuple(str(item) for item in blockers) if isinstance(blockers, (list, tuple)) else ()
    print("blocker_codes=" + (",".join(values) if values else "none"))
    print("paper_dispatch_state=disabled")
    print("broker_connection_attempts=0")
    print("broker_write_attempts=0")
    print("broker_actions_allowed=false")


@contextmanager
def daily_run_process_lock(path: Path) -> Iterator[bool]:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            yield False
            return
        yield True


def main() -> int:
    args = parse_args()
    if args.status:
        return asyncio.run(run(args))
    with daily_run_process_lock(Path("var/control/daily-run.lock")) as acquired:
        if not acquired:
            print("state=lease_held")
            print("recovery_action=查看现有运行 make daily-run-status")
            print("broker_actions_allowed=false")
            return 0
        return asyncio.run(run(args))


if __name__ == "__main__":
    raise SystemExit(main())
