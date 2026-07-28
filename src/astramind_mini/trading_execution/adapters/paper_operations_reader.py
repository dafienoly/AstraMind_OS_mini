"""Read-only projection for Paper operations and UI."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, cast

from ..contracts.paper_canary import PaperCanaryAuthorization
from ..contracts.paper_continuous import PaperOperationsSnapshot
from .shadow_ledger import ShadowLedger


class PaperOperationsReader:
    def __init__(self, database: Path) -> None:
        self._database = database
        self._ledger = ShadowLedger(database)

    def current(self) -> PaperOperationsSnapshot:
        self._ledger.migrate()
        with sqlite3.connect(self._database) as connection:
            authorization = self._authorization(connection)
            baseline = self._latest_payload(connection, "paper_account_baselines")
            proposal = self._latest_payload(connection, "paper_limit_proposals")
            approval = self._latest_payload(connection, "paper_submission_approvals")
            projection = self._latest_payload(connection, "paper_order_projections")
            convergence = self._latest_payload(connection, "paper_convergence_reports")
            intent_count = self._count(connection, "paper_order_intents")
            observation_count = self._count(connection, "paper_order_observations")
        if authorization is None:
            return self._empty(baseline, intent_count, observation_count)
        baseline_state = _baseline_state(baseline)
        blockers = _blockers(authorization, baseline, proposal, approval, projection)
        state = _canary_state(authorization, approval, projection, convergence, blockers)
        return PaperOperationsSnapshot(
            as_of=datetime.now(UTC),
            execution_mode="paper",
            account_mode="simulation",
            broker_connection="disconnected",
            canary_state=state,
            standing_mandate_id=authorization.standing_mandate.standing_mandate_id,
            authorization_id=authorization.authorization_id,
            instrument_id=authorization.instrument_id,
            side=authorization.side,
            quantity=authorization.quantity,
            max_notional_cny=authorization.max_notional_cny,
            mandate_effective_from=authorization.standing_mandate.effective_from,
            mandate_effective_to=authorization.standing_mandate.effective_to,
            submission_window_start=authorization.submission_window_start,
            submission_window_end=authorization.submission_window_end,
            inherited_overlap=authorization.inherited_overlap,
            account_baseline_state=baseline_state,
            inherited_position_count=_baseline_count(baseline, "inherited_position_count"),
            open_order_count=len(_baseline_items(baseline, "open_order_fingerprints")),
            intent_count=intent_count,
            observation_count=observation_count,
            blocker_codes=blockers,
            next_action=_next_action(blockers),
            broker_actions_allowed=False,
        )

    @staticmethod
    def _authorization(connection: sqlite3.Connection) -> PaperCanaryAuthorization | None:
        row = connection.execute(
            "SELECT payload_json FROM paper_canary_authorizations ORDER BY rowid DESC LIMIT 1"
        ).fetchone()
        return PaperCanaryAuthorization.model_validate_json(row[0]) if row else None

    @staticmethod
    def _latest_payload(connection: sqlite3.Connection, table: str) -> dict[str, Any] | None:
        row = connection.execute(
            f"SELECT payload_json FROM {table} ORDER BY rowid DESC LIMIT 1"
        ).fetchone()
        return cast(dict[str, Any], json.loads(str(row[0]))) if row else None

    @staticmethod
    def _count(connection: sqlite3.Connection, table: str) -> int:
        return int(connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0])

    @staticmethod
    def _empty(
        baseline: dict[str, Any] | None, intent_count: int, observation_count: int
    ) -> PaperOperationsSnapshot:
        return PaperOperationsSnapshot(
            as_of=datetime.now(UTC),
            execution_mode="paper",
            account_mode="simulation",
            broker_connection="disconnected",
            canary_state="not_authorized",
            standing_mandate_id=None,
            authorization_id=None,
            instrument_id=None,
            side=None,
            mandate_effective_from=None,
            mandate_effective_to=None,
            submission_window_start=None,
            submission_window_end=None,
            inherited_overlap=None,
            account_baseline_state=_baseline_state(baseline),
            inherited_position_count=_baseline_count(baseline, "inherited_position_count"),
            open_order_count=len(_baseline_items(baseline, "open_order_fingerprints")),
            intent_count=intent_count,
            observation_count=observation_count,
            blocker_codes=("standing_mandate_missing",),
            next_action="批准准确 Paper StandingMandate",
            broker_actions_allowed=False,
        )


def _baseline_state(
    value: dict[str, Any] | None,
) -> Literal["missing", "readonly_ready", "blocked"]:
    if value is None:
        return "missing"
    state = str(value.get("startup_state", "blocked"))
    if state == "readonly_ready":
        return "readonly_ready"
    return "blocked"


def _baseline_count(value: dict[str, Any] | None, key: str) -> int:
    raw = value.get(key, 0) if value else 0
    return int(raw) if isinstance(raw, int) and raw >= 0 else 0


def _baseline_items(value: dict[str, Any] | None, key: str) -> tuple[object, ...]:
    raw = value.get(key, []) if value else []
    return tuple(raw) if isinstance(raw, list | tuple) else ()


def _blockers(
    authorization: PaperCanaryAuthorization,
    baseline: dict[str, Any] | None,
    proposal: dict[str, Any] | None,
    approval: dict[str, Any] | None,
    projection: dict[str, Any] | None,
) -> tuple[str, ...]:
    result: list[str] = []
    if proposal is None:
        result.append("fresh_limit_proposal_required")
    if approval is None:
        result.append("final_limit_approval_required")
    if baseline is None:
        result.append("paper_account_baseline_missing")
    if _baseline_items(baseline, "open_order_fingerprints"):
        result.append("unexpected_open_orders")
    if projection and projection.get("state") == "submission_unknown":
        result.append("submission_unknown_query_only")
    if datetime.now(UTC) > authorization.submission_window_end:
        result.append("mandate_window_expired")
    return tuple(sorted(result))


def _canary_state(
    authorization: PaperCanaryAuthorization,
    approval: dict[str, Any] | None,
    projection: dict[str, Any] | None,
    convergence: dict[str, Any] | None,
    blockers: tuple[str, ...],
) -> Literal[
    "awaiting_final_limit_approval",
    "ready_to_submit",
    "working",
    "terminal",
    "blocked",
]:
    if convergence and convergence.get("status") == "converged":
        return "terminal"
    if projection:
        state = str(projection.get("state"))
        if state in {"filled", "cancelled", "rejected"}:
            return "terminal"
        if state in {"acknowledged", "partially_filled", "cancel_pending"}:
            return "working"
        return "blocked"
    if "mandate_window_expired" in blockers:
        return "blocked"
    if approval is not None and not blockers:
        return "ready_to_submit"
    return authorization.state


def _next_action(blockers: tuple[str, ...]) -> str:
    if "mandate_window_expired" in blockers:
        return "本次 Mandate 已过期，禁止提交"
    if "paper_account_baseline_missing" in blockers:
        return "重新建立 MiniQMT 模拟盘只读基线"
    if "unexpected_open_orders" in blockers:
        return "先处理模拟盘已有未完成委托"
    if "submission_unknown_query_only" in blockers:
        return "按幂等标记查询恢复，禁止重提"
    if "fresh_limit_proposal_required" in blockers:
        return "在提交窗口建立新账户基线并读取新鲜卖一"
    return "在提交窗口读取新鲜卖一并确认确切限价"


__all__ = ["PaperOperationsReader"]
