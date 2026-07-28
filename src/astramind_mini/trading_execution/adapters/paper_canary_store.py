"""Append-only storage for Paper canary authorization evidence."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from ..contracts.paper_canary import PaperCanaryAuthorization
from .shadow_ledger import ShadowLedger


class PaperCanaryAuthorizationStore:
    def __init__(self, database: Path) -> None:
        self._database = database
        self._ledger = ShadowLedger(database)

    def publish(self, value: PaperCanaryAuthorization) -> None:
        self._ledger.migrate()
        encoded = value.model_dump_json()
        with self._connect() as connection:
            existing = connection.execute(
                "SELECT payload_json FROM paper_canary_authorizations WHERE identity = ?",
                (value.authorization_id,),
            ).fetchone()
            if existing is not None:
                if str(existing[0]) != encoded:
                    raise ValueError("Paper 金丝雀授权身份发生内容冲突")
                return
            connection.execute(
                "INSERT INTO paper_canary_authorizations VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    value.authorization_id,
                    value.standing_mandate.standing_mandate_id,
                    value.source_portfolio_target_id,
                    value.account_baseline_id,
                    value.state,
                    value.content_hash,
                    encoded,
                ),
            )

    def read(self, identity: str) -> PaperCanaryAuthorization:
        self._ledger.migrate()
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM paper_canary_authorizations WHERE identity = ?",
                (identity,),
            ).fetchone()
        if row is None:
            raise KeyError(identity)
        return PaperCanaryAuthorization.model_validate_json(row[0])

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._database)
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        return connection


__all__ = ["PaperCanaryAuthorizationStore"]
