"""Append-only SQLite/WAL store for continuous Shadow control records."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from astramind_mini.contracts import ExecutionEvent

from ..contracts.continuous_shadow import (
    ContinuousShadowCycle,
    ContinuousShadowOrderPlan,
    ContinuousShadowState,
    ReconciliationDisposition,
)
from ..contracts.shadow_cycle import ShadowCycleCheckpoint, ShadowCycleResult
from ..domain.reconciliation import canonical_hash
from .shadow_cycle_identity import checkpoint_identity, result_identity
from .shadow_ledger import ShadowLedger


class ContinuousShadowStore:
    def __init__(self, database: Path) -> None:
        self._database = database
        self._ledger = ShadowLedger(database)

    def migrate(self) -> None:
        self._ledger.migrate()

    def publish_disposition(self, value: ReconciliationDisposition) -> None:
        expected = {
            "account_snapshot_id": value.account_snapshot_id,
            "reconciliation_report_id": value.reconciliation_report_id,
            "local_projection_id": value.local_projection_id,
            "resolution_kind": value.resolution_kind,
            "local_shadow_authority": value.local_shadow_authority,
            "resolved_blocker_codes": sorted(value.resolved_blocker_codes),
            "policy_version": value.policy_version,
            "created_at": value.created_at,
        }
        self._verify(
            value.content_hash, value.disposition_id, "reconciliation-disposition:", expected
        )
        self._insert(
            "reconciliation_dispositions",
            (
                value.disposition_id,
                value.reconciliation_report_id,
                value.content_hash,
                value.model_dump_json(),
                value.created_at.isoformat(),
            ),
        )

    def publish_state(self, value: ContinuousShadowState) -> None:
        expected = {
            "disposition_id": value.disposition_id,
            "trading_date": value.trading_date,
            "as_of": value.as_of,
            "cash_cny": value.cash_cny,
            "positions": [item.model_dump(mode="json") for item in value.positions],
            "realized_profit_cny": value.realized_profit_cny,
            "equity_cny": value.equity_cny,
            "sleeve_peak_equity_cny": value.sleeve_peak_equity_cny,
            "account_equity_cny": value.account_equity_cny,
            "account_peak_equity_cny": value.account_peak_equity_cny,
        }
        self._verify(value.content_hash, value.state_id, "continuous-shadow-state:", expected)
        self._insert(
            "continuous_shadow_states",
            (
                value.state_id,
                value.disposition_id,
                value.trading_date.isoformat(),
                value.content_hash,
                value.model_dump_json(),
                value.as_of.isoformat(),
            ),
        )

    def publish_order_plan(self, value: ContinuousShadowOrderPlan) -> None:
        self._insert(
            "continuous_shadow_order_plans",
            (
                value.order_plan.order_plan_id,
                value.state_id,
                value.order_plan.portfolio_target_id,
                value.status,
                value.content_hash,
                value.model_dump_json(),
                value.order_plan.created_at.isoformat(),
            ),
        )

    def publish_cycle(self, value: ContinuousShadowCycle) -> None:
        expected = {
            "promotion_decision_id": value.promotion_decision_id,
            "data_snapshot_id": value.data_snapshot_id,
            "feature_snapshot_id": value.feature_snapshot_id,
            "prediction_batch_id": value.prediction_batch_id,
            "portfolio_target_id": value.portfolio_target_id,
            "order_plan_id": value.order_plan_id,
            "signal_date": value.signal_date,
            "nominal_execution_date": value.nominal_execution_date,
            "scheduled_execution_date": value.scheduled_execution_date,
            "status": value.status,
            "warning_codes": value.warning_codes,
            "created_at": value.created_at,
        }
        self._verify(
            value.content_hash,
            value.cycle_id,
            "continuous-shadow-cycle:",
            expected,
        )
        self._insert(
            "continuous_shadow_cycles",
            (
                value.cycle_id,
                value.order_plan_id,
                value.status,
                value.content_hash,
                value.model_dump_json(),
                value.created_at.isoformat(),
            ),
        )

    def read_disposition(self, identity: str) -> ReconciliationDisposition:
        return ReconciliationDisposition.model_validate_json(
            self._payload("reconciliation_dispositions", identity)
        )

    def read_state(self, identity: str) -> ContinuousShadowState:
        return ContinuousShadowState.model_validate_json(
            self._payload("continuous_shadow_states", identity)
        )

    def latest_state(self) -> ContinuousShadowState | None:
        self.migrate()
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM continuous_shadow_states "
                "ORDER BY created_at DESC, identity DESC LIMIT 1"
            ).fetchone()
        return ContinuousShadowState.model_validate_json(row[0]) if row else None

    def read_cycle(self, identity: str) -> ContinuousShadowCycle:
        return ContinuousShadowCycle.model_validate_json(
            self._payload("continuous_shadow_cycles", identity)
        )

    def read_order_plan(self, identity: str) -> ContinuousShadowOrderPlan:
        return ContinuousShadowOrderPlan.model_validate_json(
            self._payload("continuous_shadow_order_plans", identity)
        )

    def publish_checkpoint(self, value: ShadowCycleCheckpoint) -> None:
        expected = checkpoint_identity(value)
        self._verify(
            value.content_hash,
            value.checkpoint_id,
            "shadow-cycle-checkpoint:",
            expected,
        )
        self._insert(
            "continuous_shadow_checkpoints",
            (
                value.checkpoint_id,
                value.cycle_id,
                value.trading_date.isoformat(),
                value.status,
                value.state_id,
                value.model_dump_json(),
                value.recorded_at.isoformat(),
            ),
        )

    def latest_checkpoint(self, cycle_id: str) -> ShadowCycleCheckpoint | None:
        self.migrate()
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM continuous_shadow_checkpoints "
                "WHERE cycle_id = ? ORDER BY trading_date DESC, created_at DESC LIMIT 1",
                (cycle_id,),
            ).fetchone()
        return ShadowCycleCheckpoint.model_validate_json(row[0]) if row else None

    def checkpoints_for(self, cycle_id: str) -> tuple[ShadowCycleCheckpoint, ...]:
        self.migrate()
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT payload_json FROM continuous_shadow_checkpoints "
                "WHERE cycle_id = ? ORDER BY trading_date, created_at",
                (cycle_id,),
            ).fetchall()
        return tuple(ShadowCycleCheckpoint.model_validate_json(row[0]) for row in rows)

    def publish_result(self, value: ShadowCycleResult) -> None:
        self._verify(
            value.content_hash,
            value.result_id,
            "shadow-cycle-result:",
            result_identity(value),
        )
        self._insert(
            "continuous_shadow_results",
            (
                value.result_id,
                value.cycle_id,
                value.status,
                value.model_dump_json(),
                value.completed_at.isoformat(),
            ),
        )

    def read_result_for_cycle(self, cycle_id: str) -> ShadowCycleResult | None:
        self.migrate()
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM continuous_shadow_results WHERE cycle_id = ?",
                (cycle_id,),
            ).fetchone()
        return ShadowCycleResult.model_validate_json(row[0]) if row else None

    def event_count_for_cycle(self, cycle_id: str) -> int:
        self.migrate()
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT count(*)
                FROM shadow_events e
                WHERE e.order_plan_id IN (
                    SELECT json_extract(payload_json, '$.entry_order_plan_id')
                    FROM continuous_shadow_checkpoints WHERE cycle_id = ?
                    UNION
                    SELECT json_extract(payload_json, '$.exit_order_plan_id')
                    FROM continuous_shadow_checkpoints WHERE cycle_id = ?
                )
                """,
                (cycle_id, cycle_id),
            ).fetchone()
        return int(row[0])

    def counts(self) -> tuple[int, int, int]:
        self.migrate()
        with self._connect() as connection:
            tables = (
                "reconciliation_dispositions",
                "continuous_shadow_states",
                "continuous_shadow_order_plans",
            )
            values = [
                int(connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0])
                for table in tables
            ]
        return values[0], values[1], values[2]

    def cycle_count(self) -> int:
        self.migrate()
        with self._connect() as connection:
            return int(
                connection.execute("SELECT count(*) FROM continuous_shadow_cycles").fetchone()[0]
            )

    def journal_mode(self) -> str:
        return self._ledger.journal_mode()

    def append_shadow_event(self, event: ExecutionEvent, payload: object) -> None:
        self._ledger.append(event, payload)

    def _payload(self, table: str, identity: str) -> str:
        self.migrate()
        with self._connect() as connection:
            row = connection.execute(
                f"SELECT payload_json FROM {table} WHERE identity = ?", (identity,)
            ).fetchone()
        if row is None:
            raise KeyError(identity)
        return str(row[0])

    def _insert(self, table: str, values: tuple[object, ...]) -> None:
        self.migrate()
        identity = str(values[0])
        payload_index = {
            "reconciliation_dispositions": 3,
            "continuous_shadow_states": 4,
            "continuous_shadow_order_plans": 5,
            "continuous_shadow_cycles": 4,
            "continuous_shadow_checkpoints": 5,
            "continuous_shadow_results": 3,
        }[table]
        encoded = str(values[payload_index])
        with self._connect() as connection:
            existing = connection.execute(
                f"SELECT payload_json FROM {table} WHERE identity = ?", (identity,)
            ).fetchone()
            if existing is not None:
                if str(existing[0]) != encoded:
                    raise ValueError("持续 Shadow 身份发生内容冲突")
                return
            placeholders = ",".join("?" for _ in values)
            connection.execute(f"INSERT INTO {table} VALUES ({placeholders})", values)

    @staticmethod
    def _verify(content_hash: str, identity: str, prefix: str, payload: object) -> None:
        digest = canonical_hash(payload)
        if content_hash != digest or identity != prefix + digest.removeprefix("sha256:"):
            raise ValueError("持续 Shadow 内容身份校验失败")

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._database)
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        return connection


__all__ = ["ContinuousShadowStore"]
