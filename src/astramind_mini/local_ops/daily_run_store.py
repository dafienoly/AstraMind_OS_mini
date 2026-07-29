"""SQLite/WAL control state and immutable summaries for WP-0030."""

from __future__ import annotations

import json
import os
import sqlite3
import tempfile
from datetime import datetime
from pathlib import Path

from .contracts import DailyRunStatus, DailyRunStep, DailyRunStepId, DailyRunSummary


class DailyRunLeaseUnavailable(RuntimeError):
    """Raised when another live owner holds the daily-run lease."""


class DailyRunStore:
    def __init__(self, database: Path, artifact_root: Path) -> None:
        self._database = database
        self._root = artifact_root

    def migrate(self) -> None:
        self._database.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS daily_run_leases (
                    run_id TEXT PRIMARY KEY,
                    owner_id TEXT NOT NULL,
                    expires_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS daily_run_status (
                    run_id TEXT PRIMARY KEY,
                    target_date TEXT NOT NULL,
                    state TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS daily_run_steps (
                    run_id TEXT NOT NULL,
                    step_id TEXT NOT NULL,
                    state TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    PRIMARY KEY (run_id, step_id)
                );
                CREATE TABLE IF NOT EXISTS daily_run_summaries (
                    summary_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL UNIQUE,
                    target_date TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS daily_run_step_history (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    step_id TEXT NOT NULL,
                    state TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    superseded_at TEXT NOT NULL,
                    recovery_reason TEXT NOT NULL,
                    UNIQUE (run_id, step_id, content_hash)
                );
                CREATE TABLE IF NOT EXISTS daily_run_summary_history (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    summary_id TEXT NOT NULL UNIQUE,
                    run_id TEXT NOT NULL,
                    target_date TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    superseded_at TEXT NOT NULL,
                    recovery_reason TEXT NOT NULL
                );
                """
            )

    def acquire_lease(
        self,
        *,
        run_id: str,
        owner_id: str,
        acquired_at: datetime,
        expires_at: datetime,
    ) -> None:
        self.migrate()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT owner_id, expires_at FROM daily_run_leases WHERE run_id = ?",
                (run_id,),
            ).fetchone()
            held_by_other = bool(row and str(row[0]) != owner_id)
            lease_is_live = bool(row and datetime.fromisoformat(str(row[1])) > acquired_at)
            if held_by_other and lease_is_live:
                raise DailyRunLeaseUnavailable("同一日常运行已有未过期实例")
            connection.execute(
                """
                INSERT INTO daily_run_leases (run_id, owner_id, expires_at)
                VALUES (?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                  owner_id=excluded.owner_id, expires_at=excluded.expires_at
                """,
                (run_id, owner_id, expires_at.isoformat()),
            )

    def release_lease(self, *, run_id: str, owner_id: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM daily_run_leases WHERE run_id = ? AND owner_id = ?",
                (run_id, owner_id),
            )

    def publish_status(self, value: DailyRunStatus) -> None:
        self.migrate()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO daily_run_status
                  (run_id, target_date, state, updated_at, content_hash, payload_json)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                  state=excluded.state, updated_at=excluded.updated_at,
                  content_hash=excluded.content_hash, payload_json=excluded.payload_json
                """,
                (
                    value.run_id,
                    value.target_date.isoformat(),
                    value.state,
                    value.updated_at.isoformat(),
                    value.content_hash,
                    value.model_dump_json(),
                ),
            )

    def status(self, run_id: str) -> DailyRunStatus | None:
        self.migrate()
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM daily_run_status WHERE run_id = ?",
                (run_id,),
            ).fetchone()
        return DailyRunStatus.model_validate_json(row[0]) if row else None

    def latest_status(self) -> DailyRunStatus | None:
        self.migrate()
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT payload_json FROM daily_run_status
                ORDER BY target_date DESC, updated_at DESC, run_id DESC LIMIT 1
                """
            ).fetchone()
        return DailyRunStatus.model_validate_json(row[0]) if row else None

    def recent_statuses(self, limit: int = 7) -> tuple[DailyRunStatus, ...]:
        if limit < 1 or limit > 30:
            raise ValueError("日常运行历史条数必须在 1 到 30 之间")
        self.migrate()
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT payload_json FROM daily_run_status
                ORDER BY target_date DESC, updated_at DESC, run_id DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return tuple(DailyRunStatus.model_validate_json(row[0]) for row in rows)

    def publish_step(self, value: DailyRunStep) -> None:
        self.migrate()
        existing = self.step(value.run_id, value.step_id)
        if existing and existing.state == "completed" and existing != value:
            raise ValueError("已完成的日常运行步骤不可改写")
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO daily_run_steps
                  (run_id, step_id, state, content_hash, payload_json)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(run_id, step_id) DO UPDATE SET
                  state=excluded.state, content_hash=excluded.content_hash,
                  payload_json=excluded.payload_json
                """,
                (
                    value.run_id,
                    value.step_id,
                    value.state,
                    value.content_hash,
                    value.model_dump_json(),
                ),
            )

    def step(self, run_id: str, step_id: DailyRunStepId) -> DailyRunStep | None:
        self.migrate()
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT payload_json FROM daily_run_steps
                WHERE run_id = ? AND step_id = ?
                """,
                (run_id, step_id),
            ).fetchone()
        return DailyRunStep.model_validate_json(row[0]) if row else None

    def prepare_recovery(self, run_id: str, prepared_at: datetime) -> tuple[int, int]:
        """Reopen a completed run while retaining its prior steps and summary."""
        self.migrate()
        with self._connect() as connection:
            status = connection.execute(
                "SELECT state FROM daily_run_status WHERE run_id = ?",
                (run_id,),
            ).fetchone()
            if status is None or status[0] != "current":
                raise ValueError("只有已完成的日常运行可显式重建")
            audit = (prepared_at.isoformat(), "explicit_recovery", run_id)
            connection.execute(
                """
                INSERT OR IGNORE INTO daily_run_step_history
                  (run_id, step_id, state, content_hash, payload_json,
                   superseded_at, recovery_reason)
                SELECT run_id, step_id, state, content_hash, payload_json, ?, ?
                FROM daily_run_steps WHERE run_id = ?
                """,
                audit,
            )
            connection.execute(
                """
                INSERT OR IGNORE INTO daily_run_summary_history
                  (summary_id, run_id, target_date, content_hash, payload_json,
                   superseded_at, recovery_reason)
                SELECT summary_id, run_id, target_date, content_hash, payload_json, ?, ?
                FROM daily_run_summaries WHERE run_id = ?
                """,
                audit,
            )
            step_count = connection.execute(
                "SELECT count(*) FROM daily_run_steps WHERE run_id = ?",
                (run_id,),
            ).fetchone()
            summary_count = connection.execute(
                "SELECT count(*) FROM daily_run_summaries WHERE run_id = ?",
                (run_id,),
            ).fetchone()
            connection.execute("DELETE FROM daily_run_steps WHERE run_id = ?", (run_id,))
            connection.execute("DELETE FROM daily_run_summaries WHERE run_id = ?", (run_id,))
        return (
            int(step_count[0]) if step_count else 0,
            int(summary_count[0]) if summary_count else 0,
        )

    def summary_history(self, run_id: str) -> tuple[DailyRunSummary, ...]:
        self.migrate()
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT payload_json FROM daily_run_summary_history
                WHERE run_id = ? ORDER BY event_id
                """,
                (run_id,),
            ).fetchall()
        return tuple(DailyRunSummary.model_validate_json(row[0]) for row in rows)

    def publish_summary(self, value: DailyRunSummary) -> Path:
        self.migrate()
        payload = value.model_dump_json().encode("utf-8")
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM daily_run_summaries WHERE run_id = ?",
                (value.run_id,),
            ).fetchone()
            if row and str(row[0]).encode("utf-8") != payload:
                raise ValueError("同一日常运行摘要发生身份冲突")
            connection.execute(
                """
                INSERT OR IGNORE INTO daily_run_summaries
                  (summary_id, run_id, target_date, content_hash, payload_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    value.summary_id,
                    value.run_id,
                    value.target_date.isoformat(),
                    value.content_hash,
                    value.model_dump_json(),
                ),
            )
        digest = value.content_hash.removeprefix("sha256:")
        path = self._root / "runs" / digest / "summary.json"
        _write_immutable(path, payload)
        pointer = json.dumps(
            {
                "run_id": value.run_id,
                "summary_id": value.summary_id,
                "artifact_path": f"runs/{digest}/summary.json",
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        _atomic_write(self._root / "current.json", pointer)
        return path

    def summary(self, run_id: str) -> DailyRunSummary | None:
        self.migrate()
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM daily_run_summaries WHERE run_id = ?",
                (run_id,),
            ).fetchone()
        return DailyRunSummary.model_validate_json(row[0]) if row else None

    def journal_mode(self) -> str:
        with self._connect() as connection:
            row = connection.execute("PRAGMA journal_mode").fetchone()
        return str(row[0])

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._database, timeout=5)
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        return connection


def _write_immutable(path: Path, payload: bytes) -> None:
    if path.exists():
        if path.read_bytes() != payload:
            raise ValueError("日常运行不可变摘要身份冲突")
        return
    _atomic_write(path, payload)


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


__all__ = ["DailyRunLeaseUnavailable", "DailyRunStore"]
