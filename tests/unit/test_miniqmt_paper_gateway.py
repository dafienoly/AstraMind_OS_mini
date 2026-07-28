from __future__ import annotations

import asyncio
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from astramind_mini.contracts import ExecutionMode, OrderPlan
from astramind_mini.trading_execution.adapters.miniqmt_account import MiniQMTAccountError
from astramind_mini.trading_execution.adapters.miniqmt_paper_gateway import (
    MiniQMTPaperGateway,
)
from astramind_mini.trading_execution.adapters.paper_continuous_store import (
    PaperContinuousStore,
)
from astramind_mini.trading_execution.adapters.paper_store import PaperExecutionStore
from astramind_mini.trading_execution.application.paper_continuous import (
    ContinuousPaperExecutionService,
)
from astramind_mini.trading_execution.contracts.paper import (
    PaperOrderIntent,
    PaperOrderProjection,
)
from astramind_mini.trading_execution.contracts.paper_canary import (
    PaperCanaryAuthorization,
)
from astramind_mini.trading_execution.contracts.paper_continuous import (
    PaperLimitProposal,
    PaperSubmissionApproval,
)
from astramind_mini.trading_execution.domain import (
    build_paper_canary_authorization,
    build_paper_intent,
    build_paper_limit_proposal,
    build_paper_preflight,
    canonical_hash,
)

SHANGHAI = timezone(timedelta(hours=8))
NOW = datetime(2026, 7, 29, 9, 35, 3, tzinfo=SHANGHAI)


class StubGateway(MiniQMTPaperGateway):
    def __init__(self, *, mode: str = "simulation") -> None:
        super().__init__(
            runner=Path("unused"),
            python_command=None,
            xtquant_path=None,
            userdata_path="private",
            account_selector="private",
            account_mode=mode,
            fingerprint_key="private",
        )
        self.actions: list[str] = []

    async def _invoke(self, action: str, intent: Any) -> dict[str, Any]:
        self.actions.append(action)
        return {
            "outcome": "accepted" if action == "submit" else "not_found",
            "broker_order_fingerprint": "sha256:" + "b" * 64 if action == "submit" else None,
            "broker_status_code": "50" if action == "submit" else None,
            "cumulative_filled_quantity": 0,
            "average_fill_price": None,
            "observed_at_epoch": NOW.timestamp(),
        }


class UnknownGateway(StubGateway):
    async def _invoke(self, action: str, intent: Any) -> dict[str, Any]:
        self.actions.append(action)
        if action == "submit":
            raise RuntimeError("connection_lost_after_submit")
        return {
            "outcome": "not_found",
            "broker_order_fingerprint": None,
            "broker_status_code": None,
            "cumulative_filled_quantity": 0,
            "average_fill_price": None,
            "observed_at_epoch": NOW.timestamp(),
        }


def _authorization() -> PaperCanaryAuthorization:
    return build_paper_canary_authorization(
        source_portfolio_target_id="portfolio-target:approved",
        source_shadow_order_plan_id="order-plan:shadow",
        account_baseline_id="paper-account-baseline:readonly",
        instrument_id="605208.SH",
        quantity=100,
        max_notional_cny=50_000,
        mandate_start=NOW.replace(hour=9, minute=30),
        mandate_end=NOW.replace(hour=10, minute=0),
        submission_start=NOW.replace(hour=9, minute=35),
        submission_end=NOW.replace(hour=9, minute=45),
        approved_at=NOW - timedelta(days=1),
    )


def _proposal() -> PaperLimitProposal:
    return build_paper_limit_proposal(
        authorization=_authorization(),
        best_ask=12.34,
        quote_market_time=NOW - timedelta(seconds=1),
        quote_received_at=NOW,
    )


def _approval() -> PaperSubmissionApproval:
    proposal = _proposal()
    payload = {
        "proposal_id": proposal.proposal_id,
        "authorization_id": proposal.authorization_id,
        "exact_limit_price": proposal.exact_limit_price,
        "approved_at": NOW,
        "effective_to": NOW + timedelta(minutes=2),
        "single_submission": True,
        "cancel_this_order_only": True,
        "broker_actions_allowed": True,
    }
    digest = canonical_hash(payload)
    return PaperSubmissionApproval.model_validate(
        {
            "approval_id": "paper-submission-approval:" + digest[7:],
            "content_hash": digest,
            **payload,
        }
    )


def _intent() -> PaperOrderIntent:
    authorization = _authorization()
    plan = OrderPlan(
        order_plan_id="order-plan:paper-canary",
        portfolio_target_id=authorization.source_portfolio_target_id,
        standing_mandate_id=authorization.standing_mandate.standing_mandate_id,
        execution_mode=ExecutionMode.PAPER,
        created_at=NOW,
        content_hash="sha256:" + "a" * 64,
    )
    preflight = build_paper_preflight(
        created_at=NOW,
        checks={
            "account_mode_verified": True,
            "reconciliation_matched": True,
            "quote_fresh": True,
            "trading_window_open": True,
            "tradable": True,
            "cash_sufficient": True,
            "lot_valid": True,
            "t_plus_one_valid": True,
            "drawdown_allowed": True,
            "mandate_approved": True,
        },
    )
    return build_paper_intent(
        order_plan=plan,
        line_id="paper-canary-line:1",
        instrument_id="605208.SH",
        side="buy",
        quantity=100,
        limit_price=12.34,
        preflight=preflight,
        created_at=NOW,
    )


def test_submit_requires_exact_approval_and_fresh_non_chasing_quote() -> None:
    gateway = StubGateway()
    result = asyncio.run(
        gateway.submit(
            intent=_intent(),
            authorization=_authorization(),
            proposal=_proposal(),
            approval=_approval(),
            fresh_best_ask=12.34,
            quote_market_time=NOW - timedelta(seconds=1),
            now=NOW,
        )
    )
    assert result.outcome == "accepted"
    assert gateway.actions == ["submit"]

    with pytest.raises(ValueError, match="禁止追价"):
        asyncio.run(
            gateway.submit(
                intent=_intent(),
                authorization=_authorization(),
                proposal=_proposal(),
                approval=_approval(),
                fresh_best_ask=12.35,
                quote_market_time=NOW,
                now=NOW,
            )
        )
    assert gateway.actions == ["submit"]


def test_live_mode_is_rejected_before_runner() -> None:
    gateway = StubGateway(mode="live")
    with pytest.raises(MiniQMTAccountError):
        asyncio.run(gateway.query(_intent()))
    assert gateway.actions == []


def test_continuous_service_submits_once_then_only_queries(tmp_path: Path) -> None:
    database = tmp_path / "paper.sqlite3"
    gateway = StubGateway()
    service = ContinuousPaperExecutionService(
        repository=PaperExecutionStore(database),
        commands=PaperContinuousStore(database),
        gateway=gateway,
    )

    async def submit_once() -> PaperOrderProjection:
        return await service.submit_once(
            intent=_intent(),
            authorization=_authorization(),
            proposal=_proposal(),
            approval=_approval(),
            fresh_best_ask=12.34,
            quote_market_time=NOW - timedelta(seconds=1),
            now=NOW,
        )

    first = asyncio.run(submit_once())
    second = asyncio.run(submit_once())

    assert first.state == "acknowledged"
    assert second.state == "submission_unknown"
    assert gateway.actions == ["query", "submit", "query"]
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT count(*) FROM paper_broker_commands").fetchone()[0] == 2


def test_gateway_exception_becomes_unknown_and_recovery_only_queries(tmp_path: Path) -> None:
    gateway = UnknownGateway()
    service = ContinuousPaperExecutionService(
        repository=PaperExecutionStore(tmp_path / "paper.sqlite3"),
        commands=PaperContinuousStore(tmp_path / "paper.sqlite3"),
        gateway=gateway,
    )
    intent = _intent()
    projection = asyncio.run(
        service.submit_once(
            intent=intent,
            authorization=_authorization(),
            proposal=_proposal(),
            approval=_approval(),
            fresh_best_ask=12.34,
            quote_market_time=NOW,
            now=NOW,
        )
    )
    assert projection.state == "submission_unknown"
    recovered = asyncio.run(service.recover(intent))
    assert recovered.state == "submission_unknown"
    assert gateway.actions == ["query", "submit", "query"]


def test_runner_queries_idempotency_before_submit_and_is_simulation_only() -> None:
    source = (Path(__file__).parents[2] / "scripts/miniqmt_paper_gateway_runner.py").read_text(
        encoding="utf-8"
    )
    assert '!= "simulation"' in source
    assert source.index("matches = _matching_orders(trader, account, remark)") < source.index(
        "return _submit("
    )
    assert "cancel_order_stock(" in source
    assert source.index("_validate_live_quote(config)") < source.index("trader.order_stock(")
    assert "unexpected_open_orders" in source
    assert "cash_insufficient" in source
    assert "price_chasing_forbidden" in source
    assert "order_stock_async" not in source
    assert "CREDIT_" not in source
