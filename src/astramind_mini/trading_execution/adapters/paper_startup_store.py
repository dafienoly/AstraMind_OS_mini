"""Append-only SQLite/WAL store for read-only Paper startup evidence."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from ..contracts.paper_startup import (
    BrokerAccountModeLock,
    PaperAccountBaseline,
    ReadonlyCallbackHandshake,
)
from .shadow_ledger import ShadowLedger


class PaperStartupStore:
    def __init__(self, database: Path) -> None:
        self._database = database
        self._ledger = ShadowLedger(database)

    def publish_mode_lock(
        self,
        value: BrokerAccountModeLock,
        *,
        account_snapshot_id: str,
    ) -> None:
        self._insert(
            "paper_mode_locks",
            (
                value.mode_lock_id,
                account_snapshot_id,
                value.effective_mode,
                value.content_hash,
                value.model_dump_json(),
                value.verified_at.isoformat(),
            ),
        )

    def publish_handshake(self, value: ReadonlyCallbackHandshake) -> None:
        self._insert(
            "paper_callback_handshakes",
            (
                value.handshake_id,
                value.account_snapshot_id,
                value.status,
                value.content_hash,
                value.model_dump_json(),
                value.completed_at.isoformat(),
            ),
        )

    def publish_baseline(self, value: PaperAccountBaseline) -> None:
        self._insert(
            "paper_account_baselines",
            (
                value.baseline_id,
                value.account_snapshot_id,
                value.startup_state,
                value.content_hash,
                value.model_dump_json(),
                value.created_at.isoformat(),
            ),
        )

    def read_baseline(self, identity: str) -> PaperAccountBaseline:
        self._ledger.migrate()
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM paper_account_baselines WHERE identity = ?",
                (identity,),
            ).fetchone()
        if row is None:
            raise KeyError(identity)
        return PaperAccountBaseline.model_validate_json(row[0])

    def counts(self) -> tuple[int, int, int]:
        self._ledger.migrate()
        with self._connect() as connection:
            counts = tuple(
                int(connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0])
                for table in (
                    "paper_mode_locks",
                    "paper_callback_handshakes",
                    "paper_account_baselines",
                )
            )
        return counts[0], counts[1], counts[2]

    def journal_mode(self) -> str:
        return self._ledger.journal_mode()

    def _insert(self, table: str, values: tuple[object, ...]) -> None:
        self._ledger.migrate()
        identity = str(values[0])
        encoded = str(values[4])
        with self._connect() as connection:
            existing = connection.execute(
                f"SELECT payload_json FROM {table} WHERE identity = ?",
                (identity,),
            ).fetchone()
            if existing is not None:
                if str(existing[0]) != encoded:
                    raise ValueError("Paper 启动证据身份发生内容冲突")
                return
            placeholders = ",".join("?" for _ in values)
            connection.execute(f"INSERT INTO {table} VALUES ({placeholders})", values)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._database)
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        return connection


__all__ = ["PaperStartupStore"]
