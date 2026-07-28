"""Append-only SQLite/WAL store for offline Paper evidence and projections."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from ..contracts.paper import (
    PaperBrokerObservation,
    PaperOrderIntent,
    PaperOrderProjection,
)
from .shadow_ledger import ShadowLedger


class PaperExecutionStore:
    def __init__(self, database: Path) -> None:
        self._database = database
        self._ledger = ShadowLedger(database)

    def migrate(self) -> None:
        self._ledger.migrate()

    def publish_intent(self, value: PaperOrderIntent) -> None:
        self._insert(
            "paper_order_intents",
            (
                value.intent_id,
                value.order_plan.order_plan_id,
                value.idempotency_key,
                value.content_hash,
                value.model_dump_json(),
                value.created_at.isoformat(),
            ),
        )

    def append_observation(self, value: PaperBrokerObservation) -> None:
        self._insert(
            "paper_order_observations",
            (
                value.evidence_id,
                value.intent_id,
                value.broker_sequence,
                value.received_at.isoformat(),
                value.content_hash,
                value.model_dump_json(),
            ),
        )

    def observations_for(self, intent_id: str) -> tuple[PaperBrokerObservation, ...]:
        self.migrate()
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT payload_json FROM paper_order_observations "
                "WHERE intent_id = ? ORDER BY received_at, identity",
                (intent_id,),
            ).fetchall()
        return tuple(PaperBrokerObservation.model_validate_json(row[0]) for row in rows)

    def publish_projection(self, value: PaperOrderProjection) -> None:
        self._insert(
            "paper_order_projections",
            (
                value.projection_id,
                value.intent_id,
                value.evidence_count,
                value.state,
                value.content_hash,
                value.model_dump_json(),
                value.updated_at.isoformat(),
            ),
        )

    def latest_projection(self, intent_id: str) -> PaperOrderProjection | None:
        self.migrate()
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM paper_order_projections "
                "WHERE intent_id = ? "
                "ORDER BY evidence_count DESC, updated_at DESC, identity DESC LIMIT 1",
                (intent_id,),
            ).fetchone()
        return PaperOrderProjection.model_validate_json(row[0]) if row else None

    def read_intent(self, intent_id: str) -> PaperOrderIntent:
        self.migrate()
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM paper_order_intents WHERE identity = ?",
                (intent_id,),
            ).fetchone()
        if row is None:
            raise KeyError(intent_id)
        return PaperOrderIntent.model_validate_json(row[0])

    def intent_for_order_plan(self, order_plan_id: str) -> PaperOrderIntent | None:
        self.migrate()
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM paper_order_intents WHERE order_plan_id = ? "
                "ORDER BY created_at, identity LIMIT 1",
                (order_plan_id,),
            ).fetchone()
        return PaperOrderIntent.model_validate_json(row[0]) if row else None

    def latest_intent(self) -> PaperOrderIntent:
        self.migrate()
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM paper_order_intents "
                "ORDER BY created_at DESC, identity DESC LIMIT 1"
            ).fetchone()
        if row is None:
            raise KeyError("latest:paper_order_intents")
        return PaperOrderIntent.model_validate_json(row[0])

    def counts(self) -> tuple[int, int, int]:
        self.migrate()
        with self._connect() as connection:
            counts = tuple(
                int(connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0])
                for table in (
                    "paper_order_intents",
                    "paper_order_observations",
                    "paper_order_projections",
                )
            )
        return counts[0], counts[1], counts[2]

    def journal_mode(self) -> str:
        return self._ledger.journal_mode()

    def _insert(self, table: str, values: tuple[object, ...]) -> None:
        self.migrate()
        identity = str(values[0])
        payload_index = {
            "paper_order_intents": 4,
            "paper_order_observations": 5,
            "paper_order_projections": 5,
        }[table]
        encoded = str(values[payload_index])
        with self._connect() as connection:
            existing = connection.execute(
                f"SELECT payload_json FROM {table} WHERE identity = ?",
                (identity,),
            ).fetchone()
            if existing is not None:
                if str(existing[0]) != encoded:
                    raise ValueError("Paper 身份发生内容冲突")
                return
            placeholders = ",".join("?" for _ in values)
            connection.execute(f"INSERT INTO {table} VALUES ({placeholders})", values)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._database)
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        return connection


__all__ = ["PaperExecutionStore"]
