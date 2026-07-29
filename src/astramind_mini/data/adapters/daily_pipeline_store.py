"""SQLite/WAL checkpoints and atomic commit pointer for WP-0025."""

from __future__ import annotations

import os
import sqlite3
import tempfile
from datetime import datetime
from pathlib import Path

from ..application.daily_pipeline_identity import build_commit
from ..application.identity import canonical_json
from ..contracts import (
    DailyPipelineCheckpoint,
    DailyPipelineCommit,
    DailyPipelineStatus,
)
from .control_ledger import DataControlLedger


class DailyPipelineStore:
    def __init__(self, database: Path, data_root: Path) -> None:
        self._database = database
        self._root = data_root

    def migrate(self) -> None:
        DataControlLedger(self._database).migrate()

    def publish_status(self, value: DailyPipelineStatus) -> None:
        self.migrate()
        payload = value.model_dump_json()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO daily_pipeline_events
                  (run_id, state, recorded_at, payload_json, content_hash)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    value.run_id,
                    value.state,
                    value.updated_at.isoformat(),
                    payload,
                    value.content_hash,
                ),
            )
            connection.execute(
                """
                INSERT INTO daily_pipeline_runs
                  (run_id, target_date, state, updated_at, payload_json, content_hash)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                  state=excluded.state,
                  updated_at=excluded.updated_at,
                  payload_json=excluded.payload_json,
                  content_hash=excluded.content_hash
                """,
                (
                    value.run_id,
                    value.target_date.isoformat(),
                    value.state,
                    value.updated_at.isoformat(),
                    payload,
                    value.content_hash,
                ),
            )

    def status(self, run_id: str) -> DailyPipelineStatus | None:
        self.migrate()
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM daily_pipeline_runs WHERE run_id = ?",
                (run_id,),
            ).fetchone()
        return DailyPipelineStatus.model_validate_json(row[0]) if row else None

    def latest_status(self) -> DailyPipelineStatus | None:
        self.migrate()
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT payload_json FROM daily_pipeline_runs
                ORDER BY target_date DESC, updated_at DESC, run_id DESC LIMIT 1
                """
            ).fetchone()
        return DailyPipelineStatus.model_validate_json(row[0]) if row else None

    def publish_checkpoint(self, value: DailyPipelineCheckpoint) -> None:
        self.migrate()
        payload = value.model_dump_json()
        with self._connect() as connection:
            existing = connection.execute(
                """
                SELECT content_hash FROM daily_pipeline_checkpoints
                WHERE run_id = ? AND step_id = ?
                """,
                (value.run_id, value.step_id),
            ).fetchone()
            if existing and existing[0] != value.content_hash:
                raise ValueError("同一日度运行检查点发生内容冲突")
            connection.execute(
                """
                INSERT OR IGNORE INTO daily_pipeline_checkpoints
                  (run_id, step_id, completed_at, payload_json, content_hash)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    value.run_id,
                    value.step_id,
                    value.completed_at.isoformat(),
                    payload,
                    value.content_hash,
                ),
            )

    def checkpoint(self, run_id: str, step_id: str) -> DailyPipelineCheckpoint | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT payload_json FROM daily_pipeline_checkpoints
                WHERE run_id = ? AND step_id = ?
                """,
                (run_id, step_id),
            ).fetchone()
        return DailyPipelineCheckpoint.model_validate_json(row[0]) if row else None

    def prepare_recovery(self, run_id: str, prepared_at: datetime) -> int:
        """Supersede mutable checkpoint pointers while preserving their audit trail."""
        self.migrate()
        with self._connect() as connection:
            run = connection.execute(
                "SELECT state FROM daily_pipeline_runs WHERE run_id = ?",
                (run_id,),
            ).fetchone()
            if run is None:
                raise ValueError("待恢复的日度数据运行不存在")
            if run[0] not in {
                "blocked",
                "current",
                "recovery_required",
                "waiting_provider",
            }:
                raise ValueError("当前日度数据运行状态不允许重建检查点")
            connection.execute(
                """
                INSERT OR IGNORE INTO daily_pipeline_checkpoint_history
                  (run_id, step_id, completed_at, payload_json, content_hash,
                   superseded_at, recovery_reason)
                SELECT run_id, step_id, completed_at, payload_json, content_hash, ?, ?
                FROM daily_pipeline_checkpoints
                WHERE run_id = ?
                """,
                (prepared_at.isoformat(), "explicit_recovery", run_id),
            )
            count = connection.execute(
                "SELECT count(*) FROM daily_pipeline_checkpoints WHERE run_id = ?",
                (run_id,),
            ).fetchone()
            connection.execute(
                "DELETE FROM daily_pipeline_checkpoints WHERE run_id = ?",
                (run_id,),
            )
        return int(count[0]) if count else 0

    def checkpoint_history(self, run_id: str) -> tuple[DailyPipelineCheckpoint, ...]:
        self.migrate()
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT payload_json
                FROM daily_pipeline_checkpoint_history
                WHERE run_id = ?
                ORDER BY event_id
                """,
                (run_id,),
            ).fetchall()
        return tuple(DailyPipelineCheckpoint.model_validate_json(row[0]) for row in rows)

    def commit(self, value: DailyPipelineCommit) -> Path:
        path = self._root / "current" / "daily-pipeline.json"
        payload = canonical_json(value.model_dump(mode="json"))
        digest = value.content_hash.removeprefix("sha256:")
        _write_immutable(
            self._root / "daily-pipeline-commits" / digest / "commit.json",
            payload,
        )
        if path.exists():
            current = DailyPipelineCommit.model_validate_json(path.read_text(encoding="utf-8"))
            if current.commit_id == value.commit_id and current != value:
                raise ValueError("同一日度管线提交身份发生冲突")
        _atomic_write(path, payload)
        return path

    def commit_for_run(self, run_id: str) -> DailyPipelineCommit | None:
        candidates: list[DailyPipelineCommit] = []
        current_path = self._root / "current" / "daily-pipeline.json"
        if current_path.exists():
            current = DailyPipelineCommit.model_validate_json(
                current_path.read_text(encoding="utf-8")
            )
            if current.run_id == run_id:
                candidates.append(current)
        history_root = self._root / "daily-pipeline-commits"
        for path in history_root.glob("*/commit.json"):
            value = DailyPipelineCommit.model_validate_json(path.read_text(encoding="utf-8"))
            if value.run_id == run_id:
                candidates.append(value)
        status = self.status(run_id)
        if (
            status is not None
            and status.state == "current"
            and status.data_snapshot_id is not None
            and status.rotation_snapshot_id is not None
            and status.completed_at is not None
        ):
            candidates.append(
                build_commit(
                    status.run_id,
                    status.target_date,
                    status.data_snapshot_id,
                    status.rotation_snapshot_id,
                    status.completed_at,
                )
            )
        return max(candidates, key=lambda value: value.committed_at, default=None)

    def current_commit(self) -> DailyPipelineCommit:
        path = self._root / "current" / "daily-pipeline.json"
        return DailyPipelineCommit.model_validate_json(path.read_text(encoding="utf-8"))

    def journal_mode(self) -> str:
        with self._connect() as connection:
            row = connection.execute("PRAGMA journal_mode").fetchone()
        return str(row[0])

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._database)
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        return connection


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _write_immutable(path: Path, payload: bytes) -> None:
    if path.exists():
        if path.read_bytes() != payload:
            raise ValueError("同一日度管线提交制品发生内容冲突")
        return
    _atomic_write(path, payload)


__all__ = ["DailyPipelineStore"]
