"""Append-only SQLite/WAL store for continuous Paper evidence."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from ..contracts.paper_continuous import (
    PaperBrokerCommandResult,
    PaperLimitProposal,
    PaperSubmissionApproval,
)
from .shadow_ledger import ShadowLedger


class PaperContinuousStore:
    def __init__(self, database: Path) -> None:
        self._database = database
        self._ledger = ShadowLedger(database)

    def publish_proposal(self, value: PaperLimitProposal) -> None:
        self._insert(
            "paper_limit_proposals",
            (
                value.proposal_id,
                value.authorization_id,
                value.account_baseline_id,
                value.state,
                value.content_hash,
                value.model_dump_json(),
                value.quote_received_at.isoformat(),
            ),
        )

    def publish_approval(self, value: PaperSubmissionApproval) -> None:
        self._insert(
            "paper_submission_approvals",
            (
                value.approval_id,
                value.proposal_id,
                value.authorization_id,
                value.content_hash,
                value.model_dump_json(),
                value.approved_at.isoformat(),
            ),
        )

    def append_command(self, value: PaperBrokerCommandResult) -> None:
        self._insert(
            "paper_broker_commands",
            (
                value.command_id,
                value.intent_id,
                value.action,
                value.outcome,
                value.content_hash,
                value.model_dump_json(),
                value.observed_at.isoformat(),
            ),
        )

    def _insert(self, table: str, values: tuple[object, ...]) -> None:
        self._ledger.migrate()
        identity, encoded = str(values[0]), str(values[-2])
        with sqlite3.connect(self._database) as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            existing = connection.execute(
                f"SELECT payload_json FROM {table} WHERE identity = ?", (identity,)
            ).fetchone()
            if existing is not None:
                if str(existing[0]) != encoded:
                    raise ValueError("持续 Paper 证据身份发生内容冲突")
                return
            placeholders = ",".join("?" for _ in values)
            connection.execute(f"INSERT INTO {table} VALUES ({placeholders})", values)


__all__ = ["PaperContinuousStore"]
