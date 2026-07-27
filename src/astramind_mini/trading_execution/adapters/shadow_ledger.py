"""Append-only SQLite/WAL ledger for local Shadow events."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from astramind_mini.contracts import ExecutionEvent


class ShadowLedger:
    def __init__(self, database: Path, migrations: Path | None = None) -> None:
        self._database = database
        self._migrations = migrations or Path(__file__).with_name("sqlite") / "migrations"

    def migrate(self) -> None:
        self._database.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations "
                "(version TEXT PRIMARY KEY, applied_at TEXT NOT NULL)"
            )
            applied = {
                str(row[0]) for row in connection.execute("SELECT version FROM schema_migrations")
            }
            for path in sorted(self._migrations.glob("*.sql")):
                if path.stem in applied:
                    continue
                connection.executescript(path.read_text(encoding="utf-8"))
                connection.execute(
                    "INSERT INTO schema_migrations VALUES (?, ?)",
                    (path.stem, datetime.now(UTC).isoformat()),
                )

    def append(self, event: ExecutionEvent, payload: object) -> None:
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        with self._connect() as connection:
            existing = connection.execute(
                "SELECT payload_json FROM shadow_events WHERE execution_event_id = ?",
                (event.execution_event_id,),
            ).fetchone()
            if existing is not None:
                if existing[0] != encoded:
                    raise ValueError("Shadow 事件身份发生内容冲突")
                return
            connection.execute(
                "INSERT INTO shadow_events VALUES (?, ?, ?, ?, ?, ?)",
                (
                    event.execution_event_id,
                    event.order_plan_id,
                    event.sequence,
                    event.event_type,
                    event.occurred_at.isoformat(),
                    encoded,
                ),
            )

    def events_for(self, order_plan_id: str) -> tuple[dict[str, object], ...]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT payload_json FROM shadow_events WHERE order_plan_id = ? ORDER BY sequence",
                (order_plan_id,),
            ).fetchall()
        return tuple(json.loads(str(row[0])) for row in rows)

    def journal_mode(self) -> str:
        with self._connect() as connection:
            row = connection.execute("PRAGMA journal_mode").fetchone()
        return str(row[0])

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._database)
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        return connection


__all__ = ["ShadowLedger"]
