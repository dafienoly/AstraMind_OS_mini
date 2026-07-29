"""Durable status, checkpoints and immutable artifacts for WP-0029."""

from __future__ import annotations

import os
import sqlite3
import tempfile
from pathlib import Path

from .contracts import DailyDecisionStatus
from .identity import operations_hash


class DailyDecisionStore:
    def __init__(self, database: Path, artifact_root: Path) -> None:
        self._database = database
        self._root = artifact_root

    def migrate(self) -> None:
        self._database.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS daily_decision_runs (
                    run_id TEXT PRIMARY KEY,
                    state TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS daily_decision_checkpoints (
                    run_id TEXT NOT NULL,
                    step_id TEXT NOT NULL,
                    artifact_identity TEXT NOT NULL,
                    completed_at TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    PRIMARY KEY(run_id, step_id)
                );
                """
            )

    def publish_status(self, value: DailyDecisionStatus) -> None:
        self.migrate()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO daily_decision_runs
                  (run_id, state, updated_at, content_hash, payload_json)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                  state=excluded.state, updated_at=excluded.updated_at,
                  content_hash=excluded.content_hash, payload_json=excluded.payload_json
                """,
                (
                    value.run_id,
                    value.state,
                    value.updated_at.isoformat(),
                    value.content_hash,
                    value.model_dump_json(),
                ),
            )

    def status(self, run_id: str) -> DailyDecisionStatus | None:
        self.migrate()
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM daily_decision_runs WHERE run_id = ?",
                (run_id,),
            ).fetchone()
        return DailyDecisionStatus.model_validate_json(row[0]) if row else None

    def latest_status(self) -> DailyDecisionStatus | None:
        self.migrate()
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT payload_json FROM daily_decision_runs
                ORDER BY updated_at DESC, run_id DESC LIMIT 1
                """
            ).fetchone()
        return DailyDecisionStatus.model_validate_json(row[0]) if row else None

    def checkpoint(
        self,
        *,
        run_id: str,
        step_id: str,
        artifact_identity: str,
        completed_at: str,
    ) -> None:
        digest = operations_hash(
            {
                "run_id": run_id,
                "step_id": step_id,
                "artifact_identity": artifact_identity,
                "completed_at": completed_at,
            }
        )
        self.migrate()
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT artifact_identity, content_hash
                FROM daily_decision_checkpoints
                WHERE run_id = ? AND step_id = ?
                """,
                (run_id, step_id),
            ).fetchone()
            if row:
                if str(row[0]) != artifact_identity or str(row[1]) != digest:
                    raise ValueError("决策链检查点身份冲突")
                return
            connection.execute(
                """
                INSERT INTO daily_decision_checkpoints
                VALUES (?, ?, ?, ?, ?)
                """,
                (run_id, step_id, artifact_identity, completed_at, digest),
            )

    def publish_artifact(self, run_id: str, artifact_hash: str, payload: bytes) -> Path:
        digest = artifact_hash.removeprefix("sha256:")
        if len(digest) != 64:
            raise ValueError("决策链制品哈希无效")
        path = self._root / "runs" / digest / "decision.json"
        _write_immutable(path, payload)
        pointer = (
            b'{"artifact_path":"runs/'
            + digest.encode()
            + b'/decision.json","run_id":"'
            + run_id.encode()
            + b'"}'
        )
        _atomic_write(self._root / "current.json", pointer)
        return path

    def current_artifact(self) -> Path:
        import json

        value = json.loads((self._root / "current.json").read_text(encoding="utf-8"))
        relative = Path(str(value["artifact_path"]))
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("决策链当前指针路径无效")
        return self._root / relative

    def journal_mode(self) -> str:
        with self._connect() as connection:
            row = connection.execute("PRAGMA journal_mode").fetchone()
        return str(row[0])

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._database)
        connection.execute("PRAGMA journal_mode=WAL")
        return connection


def _write_immutable(path: Path, payload: bytes) -> None:
    if path.exists():
        if path.read_bytes() != payload:
            raise ValueError("决策链不可变制品身份冲突")
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


__all__ = ["DailyDecisionStore"]
