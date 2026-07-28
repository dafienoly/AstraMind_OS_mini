"""Append-only SQLite/WAL ledger for local manual promotions."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from ..contracts import PromotionDecision


class SQLitePromotionDecisionStore:
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
                row[0] for row in connection.execute("SELECT version FROM schema_migrations")
            }
            for path in sorted(self._migrations.glob("*.sql")):
                if path.stem in applied:
                    continue
                connection.executescript(path.read_text(encoding="utf-8"))
                connection.execute(
                    "INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                    (path.stem, datetime.now(UTC).isoformat()),
                )

    def append(self, decision: PromotionDecision) -> None:
        payload = decision.model_dump_json()
        with self._connect() as connection:
            existing = connection.execute(
                "SELECT payload_json FROM promotion_decisions WHERE decision_id = ?",
                (decision.decision_id,),
            ).fetchone()
            if existing is not None:
                if str(existing[0]) != payload:
                    raise ValueError("晋级决定身份发生内容冲突")
                return
            connection.execute(
                """
                INSERT INTO promotion_decisions(
                  decision_id, strategy_version_id, evidence_bundle_id,
                  evidence_id, sleeve, outcome, decided_at, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    decision.decision_id,
                    decision.strategy_version_id,
                    decision.evidence_bundle_id,
                    decision.evidence_id,
                    decision.sleeve,
                    decision.outcome,
                    decision.decided_at.isoformat(),
                    payload,
                ),
            )

    def get(self, decision_id: str) -> PromotionDecision:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM promotion_decisions WHERE decision_id = ?",
                (decision_id,),
            ).fetchone()
        if row is None:
            raise KeyError(decision_id)
        return PromotionDecision.model_validate_json(str(row[0]))

    def latest_promoted(self, sleeve: str) -> PromotionDecision | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT payload_json FROM promotion_decisions
                WHERE sleeve = ? AND outcome = 'promoted'
                ORDER BY decided_at DESC, decision_id DESC LIMIT 1
                """,
                (sleeve,),
            ).fetchone()
        return PromotionDecision.model_validate_json(str(row[0])) if row else None

    def journal_mode(self) -> str:
        with self._connect() as connection:
            row = connection.execute("PRAGMA journal_mode").fetchone()
        return str(row[0])

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._database)
        connection.execute("PRAGMA journal_mode=WAL")
        return connection


__all__ = ["SQLitePromotionDecisionStore"]
