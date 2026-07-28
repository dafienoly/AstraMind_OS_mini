"""Append-only lookup and evidence store for the real Paper canary runtime."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel

from ..contracts.paper import PaperPreflightDecision
from ..contracts.paper_canary import PaperCanaryAuthorization
from ..contracts.paper_continuous import PaperLimitProposal, PaperSubmissionApproval
from ..contracts.paper_runtime import PaperConvergenceReport
from ..contracts.paper_startup import BrokerAccountModeLock, PaperAccountBaseline
from .shadow_ledger import ShadowLedger

Model = TypeVar("Model", bound=BaseModel)


class PaperRuntimeStore:
    def __init__(self, database: Path) -> None:
        self._database = database
        self._ledger = ShadowLedger(database)

    def authorization(self, identity: str | None = None) -> PaperCanaryAuthorization:
        return self._read("paper_canary_authorizations", PaperCanaryAuthorization, identity)

    def proposal(self, identity: str | None = None) -> PaperLimitProposal:
        return self._read("paper_limit_proposals", PaperLimitProposal, identity)

    def approval(self, identity: str | None = None) -> PaperSubmissionApproval:
        return self._read("paper_submission_approvals", PaperSubmissionApproval, identity)

    def baseline(self, identity: str | None = None) -> PaperAccountBaseline:
        return self._read("paper_account_baselines", PaperAccountBaseline, identity)

    def mode_lock(self, identity: str) -> BrokerAccountModeLock:
        return self._read("paper_mode_locks", BrokerAccountModeLock, identity)

    def publish_preflight(
        self,
        value: PaperPreflightDecision,
        *,
        authorization_id: str,
        proposal_id: str,
    ) -> None:
        state = "blocked" if value.blocker_codes else "passed"
        self._insert(
            "paper_preflight_decisions",
            (
                value.decision_id,
                authorization_id,
                proposal_id,
                state,
                value.content_hash,
                value.model_dump_json(),
                value.created_at.isoformat(),
            ),
        )

    def publish_convergence(self, value: PaperConvergenceReport) -> None:
        self._insert(
            "paper_convergence_reports",
            (
                value.report_id,
                value.intent_id,
                value.status,
                value.content_hash,
                value.model_dump_json(),
                value.created_at.isoformat(),
            ),
        )

    def account_snapshot_ids(self) -> tuple[str, ...]:
        self._ledger.migrate()
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT identity FROM account_snapshot_publications ORDER BY occurred_at, identity"
            ).fetchall()
        return tuple(str(row[0]) for row in rows)

    def convergence(self, identity: str | None = None) -> PaperConvergenceReport:
        return self._read("paper_convergence_reports", PaperConvergenceReport, identity)

    def _read(self, table: str, model: type[Model], identity: str | None) -> Model:
        self._ledger.migrate()
        with self._connect() as connection:
            if identity is None:
                row = connection.execute(
                    f"SELECT payload_json FROM {table} ORDER BY rowid DESC LIMIT 1"
                ).fetchone()
            else:
                row = connection.execute(
                    f"SELECT payload_json FROM {table} WHERE identity = ?", (identity,)
                ).fetchone()
        if row is None:
            raise KeyError(identity or f"latest:{table}")
        return model.model_validate_json(row[0])

    def _insert(self, table: str, values: tuple[object, ...]) -> None:
        self._ledger.migrate()
        identity, encoded = str(values[0]), str(values[-2])
        with self._connect() as connection:
            row = connection.execute(
                f"SELECT payload_json FROM {table} WHERE identity = ?", (identity,)
            ).fetchone()
            if row is not None:
                if str(row[0]) != encoded:
                    raise ValueError("Paper 运行证据身份发生内容冲突")
                return
            placeholders = ",".join("?" for _ in values)
            connection.execute(f"INSERT INTO {table} VALUES ({placeholders})", values)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._database)
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        return connection


__all__ = ["PaperRuntimeStore"]
