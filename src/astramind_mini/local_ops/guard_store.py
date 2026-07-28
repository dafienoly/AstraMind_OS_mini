"""SQLite/WAL checkpoints and a single-instance lease for the offline guard."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from .contracts import OfflineFaultDrillReport, OfflineGuardRun, OfflineGuardTaskResult


class GuardLeaseUnavailable(RuntimeError):
    """Raised when another non-expired owner holds the offline guard lease."""


class OfflineGuardStore:
    def __init__(self, database: Path) -> None:
        self._database = database

    def migrate(self) -> None:
        self._database.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS offline_guard_leases (
                    lease_name TEXT PRIMARY KEY,
                    owner_id TEXT NOT NULL,
                    heartbeat_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS offline_guard_task_results (
                    run_id TEXT NOT NULL,
                    task_id TEXT NOT NULL,
                    attempt INTEGER NOT NULL,
                    content_hash TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    PRIMARY KEY (run_id, task_id)
                );
                CREATE TABLE IF NOT EXISTS offline_guard_runs (
                    run_id TEXT PRIMARY KEY,
                    logical_date TEXT NOT NULL,
                    state TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS offline_fault_drills (
                    report_id TEXT PRIMARY KEY,
                    logical_date TEXT NOT NULL,
                    status TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );
                """
            )

    def acquire_lease(
        self,
        *,
        lease_name: str,
        owner_id: str,
        heartbeat_at: datetime,
        expires_at: datetime,
    ) -> None:
        self.migrate()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT owner_id, expires_at FROM offline_guard_leases WHERE lease_name = ?",
                (lease_name,),
            ).fetchone()
            if (
                row
                and str(row[0]) != owner_id
                and datetime.fromisoformat(str(row[1])) > heartbeat_at
            ):
                raise GuardLeaseUnavailable("已有未过期的离线守护实例")
            connection.execute(
                """
                INSERT INTO offline_guard_leases (lease_name, owner_id, heartbeat_at, expires_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(lease_name) DO UPDATE SET
                    owner_id = excluded.owner_id,
                    heartbeat_at = excluded.heartbeat_at,
                    expires_at = excluded.expires_at
                """,
                (lease_name, owner_id, heartbeat_at.isoformat(), expires_at.isoformat()),
            )

    def heartbeat(
        self,
        *,
        lease_name: str,
        owner_id: str,
        heartbeat_at: datetime,
        expires_at: datetime,
    ) -> None:
        with self._connect() as connection:
            changed = connection.execute(
                """
                UPDATE offline_guard_leases
                SET heartbeat_at = ?, expires_at = ?
                WHERE lease_name = ? AND owner_id = ?
                """,
                (heartbeat_at.isoformat(), expires_at.isoformat(), lease_name, owner_id),
            ).rowcount
        if changed != 1:
            raise GuardLeaseUnavailable("离线守护租约已丢失")

    def release_lease(self, *, lease_name: str, owner_id: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM offline_guard_leases WHERE lease_name = ? AND owner_id = ?",
                (lease_name, owner_id),
            )

    def task_result(self, *, run_id: str, task_id: str) -> OfflineGuardTaskResult | None:
        self.migrate()
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT payload_json FROM offline_guard_task_results
                WHERE run_id = ? AND task_id = ?
                """,
                (run_id, task_id),
            ).fetchone()
        return OfflineGuardTaskResult.model_validate_json(row[0]) if row else None

    def run(self, run_id: str) -> OfflineGuardRun | None:
        self.migrate()
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM offline_guard_runs WHERE run_id = ?",
                (run_id,),
            ).fetchone()
        return OfflineGuardRun.model_validate_json(row[0]) if row else None

    def publish_task(self, *, run_id: str, value: OfflineGuardTaskResult) -> None:
        self._publish(
            table="offline_guard_task_results",
            identity_columns=(run_id, value.task_id),
            content_hash=value.content_hash,
            payload=value.model_dump_json(),
        )

    def publish_run(self, value: OfflineGuardRun) -> None:
        self._publish(
            table="offline_guard_runs",
            identity_columns=(value.run_id, value.logical_date.isoformat(), value.state),
            content_hash=value.content_hash,
            payload=value.model_dump_json(),
        )

    def publish_drill(self, value: OfflineFaultDrillReport) -> None:
        self._publish(
            table="offline_fault_drills",
            identity_columns=(value.report_id, value.logical_date.isoformat(), value.status),
            content_hash=value.content_hash,
            payload=value.model_dump_json(),
        )

    def _publish(
        self,
        *,
        table: str,
        identity_columns: tuple[str, ...],
        content_hash: str,
        payload: str,
    ) -> None:
        self.migrate()
        identity = identity_columns[0]
        identity_column = "run_id" if table == "offline_guard_runs" else "report_id"
        if table == "offline_guard_task_results":
            identity_column = "run_id"
        with self._connect() as connection:
            if table == "offline_guard_task_results":
                row = connection.execute(
                    """
                    SELECT content_hash, payload_json FROM offline_guard_task_results
                    WHERE run_id = ? AND task_id = ?
                    """,
                    identity_columns,
                ).fetchone()
                if row:
                    if str(row[0]) != content_hash or str(row[1]) != payload:
                        raise ValueError("离线守护检查点身份发生内容冲突")
                    return
                connection.execute(
                    """
                    INSERT INTO offline_guard_task_results
                    (run_id, task_id, attempt, content_hash, payload_json)
                    VALUES (?, ?, 1, ?, ?)
                    """,
                    (*identity_columns, content_hash, payload),
                )
                return
            row = connection.execute(
                f"SELECT content_hash, payload_json FROM {table} WHERE {identity_column} = ?",
                (identity,),
            ).fetchone()
            if row:
                if str(row[0]) != content_hash or str(row[1]) != payload:
                    raise ValueError("离线运行证据身份发生内容冲突")
                return
            placeholders = ",".join("?" for _ in (*identity_columns, content_hash, payload))
            connection.execute(
                f"INSERT INTO {table} VALUES ({placeholders})",
                (*identity_columns, content_hash, payload),
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._database)
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        return connection


__all__ = ["GuardLeaseUnavailable", "OfflineGuardStore"]
