from __future__ import annotations

import subprocess
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from astramind_mini.config import Settings
from astramind_mini.data.adapters import DailyPipelineStore
from astramind_mini.data.application.daily_pipeline_identity import (
    build_commit,
    build_run_id,
    build_status,
)
from scripts.run_daily import _run_data


def _publish_current(
    store: DailyPipelineStore,
    *,
    target_date: date,
    base_snapshot_id: str,
    completed_at: datetime,
) -> tuple[str, str]:
    run_id = build_run_id(base_snapshot_id, target_date)
    snapshot_id = f"snapshot:{target_date.isoformat()}"
    rotation_id = f"rotation:{target_date.isoformat()}"
    status = build_status(
        run_id=run_id,
        target_date=target_date,
        base_snapshot_id=base_snapshot_id,
        state="current",
        current_step=None,
        attempt=1,
        expected_l1_count=31,
        expected_l2_count=124,
        observed_l1_count=31,
        observed_l2_count=124,
        data_snapshot_id=snapshot_id,
        rotation_snapshot_id=rotation_id,
        blocker_codes=(),
        recovery_action=None,
        started_at=completed_at - timedelta(minutes=5),
        updated_at=completed_at,
        completed_at=completed_at,
    )
    commit = build_commit(
        run_id,
        target_date,
        snapshot_id,
        rotation_id,
        completed_at,
    )
    store.publish_status(status)
    store.commit(commit)
    return run_id, commit.commit_id


def test_historical_run_resolves_its_exact_commit_after_newer_date(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data_root = tmp_path / "data"
    control_db = tmp_path / "control.sqlite3"
    store = DailyPipelineStore(control_db, data_root)
    older = date(2026, 7, 28)
    newer = date(2026, 7, 29)
    older_base = "snapshot:older-base"
    older_run_id, older_commit_id = _publish_current(
        store,
        target_date=older,
        base_snapshot_id=older_base,
        completed_at=datetime(2026, 7, 28, 18, 0, tzinfo=UTC),
    )
    _publish_current(
        store,
        target_date=newer,
        base_snapshot_id="snapshot:newer-base",
        completed_at=datetime(2026, 7, 29, 18, 0, tzinfo=UTC),
    )
    commands: list[list[str]] = []

    def completed(command: list[str], *, check: bool) -> subprocess.CompletedProcess[str]:
        assert not check
        commands.append(command)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(subprocess, "run", completed)
    outcome = _run_data(
        settings=Settings(
            data_dir=data_root,
            control_db_path=control_db,
        ),
        provider_env_file=tmp_path / "provider.env",
        target_date=older,
        base_snapshot_id=older_base,
        force_rebuild=False,
    )

    assert outcome.state == "completed"
    assert outcome.commit_id == older_commit_id
    assert store.commit_for_run(older_run_id) is not None
    assert "--recover" not in commands[0]


def test_forced_rebuild_keeps_explicit_pipeline_recovery_flag(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data_root = tmp_path / "data"
    control_db = tmp_path / "control.sqlite3"
    store = DailyPipelineStore(control_db, data_root)
    target = date(2026, 7, 28)
    base = "snapshot:base"
    _publish_current(
        store,
        target_date=target,
        base_snapshot_id=base,
        completed_at=datetime(2026, 7, 28, 18, 0, tzinfo=UTC),
    )
    commands: list[list[str]] = []

    def completed(command: list[str], *, check: bool) -> subprocess.CompletedProcess[str]:
        assert not check
        commands.append(command)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(subprocess, "run", completed)
    outcome = _run_data(
        settings=Settings(
            data_dir=data_root,
            control_db_path=control_db,
        ),
        provider_env_file=tmp_path / "provider.env",
        target_date=target,
        base_snapshot_id=base,
        force_rebuild=True,
    )

    assert outcome.state == "completed"
    assert "--recover" in commands[0]


def test_legacy_current_status_reconstructs_missing_commit_artifact(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "data"
    control_db = tmp_path / "control.sqlite3"
    store = DailyPipelineStore(control_db, data_root)
    target = date(2026, 7, 28)
    base = "snapshot:legacy-base"
    run_id = build_run_id(base, target)
    completed_at = datetime(2026, 7, 28, 18, 0, tzinfo=UTC)
    store.publish_status(
        build_status(
            run_id=run_id,
            target_date=target,
            base_snapshot_id=base,
            state="current",
            current_step=None,
            attempt=1,
            expected_l1_count=31,
            expected_l2_count=124,
            observed_l1_count=31,
            observed_l2_count=124,
            data_snapshot_id="snapshot:legacy",
            rotation_snapshot_id="rotation:legacy",
            blocker_codes=(),
            recovery_action=None,
            started_at=completed_at - timedelta(minutes=5),
            updated_at=completed_at,
            completed_at=completed_at,
        )
    )

    commit = store.commit_for_run(run_id)

    assert commit is not None
    assert commit.run_id == run_id
    assert commit.target_date == target
