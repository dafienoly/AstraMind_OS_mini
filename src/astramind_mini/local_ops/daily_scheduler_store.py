"""Persistent scheduler deployment, decisions, and local UI requests."""

from __future__ import annotations

import sqlite3
from datetime import date, datetime
from pathlib import Path
from typing import Literal

from .daily_scheduler_contracts import (
    DailyRunRequest,
    DailyScheduleDecision,
    DailyScheduleDeployment,
)
from .identity import operations_hash


class DailySchedulerStore:
    def __init__(self, database: Path) -> None:
        self._database = database

    def migrate(self) -> None:
        self._database.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS daily_schedule_decisions (
                    decision_id TEXT PRIMARY KEY,
                    evaluated_at TEXT NOT NULL,
                    target_date TEXT,
                    action TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    content_hash TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS daily_schedule_deployment (
                    deployment_id TEXT PRIMARY KEY,
                    state TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    content_hash TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS daily_run_requests (
                    request_id TEXT PRIMARY KEY,
                    request_key TEXT NOT NULL UNIQUE,
                    state TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    content_hash TEXT NOT NULL
                );
                """
            )

    def publish_decision(self, value: DailyScheduleDecision) -> None:
        self.migrate()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO daily_schedule_decisions
                  (decision_id, evaluated_at, target_date, action, payload_json, content_hash)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    value.decision_id,
                    value.evaluated_at.isoformat(),
                    value.target_date.isoformat() if value.target_date else None,
                    value.action,
                    value.model_dump_json(),
                    value.content_hash,
                ),
            )

    def latest_decision(self) -> DailyScheduleDecision | None:
        self.migrate()
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT payload_json FROM daily_schedule_decisions
                ORDER BY evaluated_at DESC, decision_id DESC LIMIT 1
                """
            ).fetchone()
        return DailyScheduleDecision.model_validate_json(row[0]) if row else None

    def publish_deployment(self, value: DailyScheduleDeployment) -> None:
        self.migrate()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO daily_schedule_deployment
                  (deployment_id, state, updated_at, payload_json, content_hash)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(deployment_id) DO UPDATE SET
                  state=excluded.state, updated_at=excluded.updated_at,
                  payload_json=excluded.payload_json, content_hash=excluded.content_hash
                """,
                (
                    value.deployment_id,
                    value.state,
                    value.updated_at.isoformat(),
                    value.model_dump_json(),
                    value.content_hash,
                ),
            )

    def deployment(self) -> DailyScheduleDeployment | None:
        self.migrate()
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT payload_json FROM daily_schedule_deployment
                WHERE deployment_id = 'daily-ops-scheduler'
                """
            ).fetchone()
        return DailyScheduleDeployment.model_validate_json(row[0]) if row else None

    def register_request(
        self,
        *,
        action: Literal["run", "recover", "retry_provider"],
        target_date: date | None,
        run_id: str | None,
        created_at: datetime,
    ) -> DailyRunRequest:
        if created_at.tzinfo is None:
            raise ValueError("本地运行请求时间必须带时区")
        request_key = _request_key(action, target_date, run_id)
        existing = self.request_by_key(request_key)
        if existing:
            return existing
        identity = {
            "request_key": request_key,
            "action": action,
            "target_date": target_date,
            "run_id": run_id,
            "state": "pending",
            "origin": "local_ui",
            "created_at": created_at,
            "updated_at": created_at,
            "broker_actions_allowed": False,
        }
        digest = operations_hash(identity)
        value = DailyRunRequest.model_validate(
            {
                **identity,
                "request_id": "daily-run-request:" + digest.removeprefix("sha256:"),
                "content_hash": digest,
            }
        )
        self.migrate()
        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO daily_run_requests
                      (request_id, request_key, state, created_at, updated_at,
                       payload_json, content_hash)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        value.request_id,
                        value.request_key,
                        value.state,
                        value.created_at.isoformat(),
                        value.updated_at.isoformat(),
                        value.model_dump_json(),
                        value.content_hash,
                    ),
                )
            return value
        except sqlite3.IntegrityError:
            concurrent = self.request_by_key(request_key)
            if concurrent is None:
                raise
            return concurrent

    def pending_request(self) -> DailyRunRequest | None:
        self.migrate()
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT payload_json FROM daily_run_requests
                WHERE state IN ('pending', 'claimed')
                ORDER BY created_at, request_id LIMIT 1
                """
            ).fetchone()
        return DailyRunRequest.model_validate_json(row[0]) if row else None

    def claim_pending(self, updated_at: datetime) -> DailyRunRequest | None:
        value = self.pending_request()
        if value is None or value.state == "claimed":
            return value
        return self._transition(value, "claimed", updated_at)

    def complete_request(self, value: DailyRunRequest, updated_at: datetime) -> DailyRunRequest:
        return self._transition(value, "completed", updated_at)

    def request_by_key(self, request_key: str) -> DailyRunRequest | None:
        self.migrate()
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM daily_run_requests WHERE request_key = ?",
                (request_key,),
            ).fetchone()
        return DailyRunRequest.model_validate_json(row[0]) if row else None

    def _transition(
        self,
        value: DailyRunRequest,
        state: Literal["claimed", "completed", "superseded"],
        updated_at: datetime,
    ) -> DailyRunRequest:
        payload = value.model_dump()
        payload.update(state=state, updated_at=updated_at)
        payload.pop("content_hash")
        payload["content_hash"] = operations_hash(payload)
        changed = DailyRunRequest.model_validate(payload)
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE daily_run_requests
                SET state = ?, updated_at = ?, payload_json = ?, content_hash = ?
                WHERE request_id = ?
                """,
                (
                    changed.state,
                    changed.updated_at.isoformat(),
                    changed.model_dump_json(),
                    changed.content_hash,
                    changed.request_id,
                ),
            )
        return changed

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._database, timeout=5)
        connection.execute("PRAGMA journal_mode=WAL")
        return connection


def _request_key(
    action: str,
    target_date: date | None,
    run_id: str | None,
) -> str:
    digest = operations_hash(
        {
            "action": action,
            "target_date": target_date,
            "run_id": run_id,
            "origin": "local_ui",
        }
    )
    return "daily-run-request-key:" + digest.removeprefix("sha256:")


__all__ = ["DailySchedulerStore"]
