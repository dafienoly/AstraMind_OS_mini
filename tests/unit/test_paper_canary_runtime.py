from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from astramind_mini.config import Settings
from astramind_mini.paper_canary_workflow import (
    PaperCanaryWorkflow,
    StagedCanary,
    expected_approval_text,
    workflow_start_delay,
)
from astramind_mini.trading_execution.adapters.miniqmt_account_normalization import (
    build_account_snapshot,
)
from astramind_mini.trading_execution.adapters.paper_runtime_store import PaperRuntimeStore
from astramind_mini.trading_execution.contracts.account import AccountSnapshot
from astramind_mini.trading_execution.contracts.paper import (
    PaperOrderProjection,
    PaperOrderState,
)
from astramind_mini.trading_execution.contracts.paper_canary import PaperCanaryAuthorization
from astramind_mini.trading_execution.contracts.paper_continuous import (
    PaperLimitProposal,
    PaperSubmissionApproval,
)
from astramind_mini.trading_execution.contracts.paper_startup import (
    BrokerAccountModeLock,
    PaperAccountBaseline,
)
from astramind_mini.trading_execution.domain import (
    build_callback_handshake,
    build_mode_lock,
    build_paper_account_baseline,
    build_paper_canary_authorization,
    build_paper_canary_order_plan,
    build_paper_limit_proposal,
    build_real_paper_preflight,
    build_submission_approval,
)
from astramind_mini.trading_execution.domain.paper_runtime import build_convergence_report

SHANGHAI = timezone(timedelta(hours=8))
NOW = datetime(2026, 7, 29, 9, 36, tzinfo=SHANGHAI)
HASH = "sha256:" + "a" * 64


def _snapshot(
    *,
    cash: float = 20_000,
    quantity: int = 100,
    open_order: bool = False,
    with_trade: bool = False,
) -> AccountSnapshot:
    order = {
        "order_fingerprint": HASH,
        "instrument_id": "605208.SH",
        "side": "buy",
        "status": "50" if open_order else "55",
        "quantity": 100,
        "filled_quantity": 0 if open_order else 100,
        "price": 12.34,
        "occurred_at": NOW,
        "is_open": open_order,
    }
    trade = {
        "trade_fingerprint": "sha256:" + "b" * 64,
        "order_fingerprint": HASH,
        "instrument_id": "605208.SH",
        "side": "buy",
        "quantity": 100,
        "price": 12.34,
        "amount_cny": 1_234,
        "occurred_at": NOW,
    }
    return build_account_snapshot(
        account_mode="simulation",
        account_fingerprint="sha256:" + "c" * 64,
        as_of=NOW,
        asset={
            "cash_cny": cash,
            "frozen_cash_cny": 0,
            "market_value_cny": quantity * 12.34,
            "total_asset_cny": cash + quantity * 12.34,
        },
        positions=[
            {
                "instrument_id": "605208.SH",
                "quantity": quantity,
                "available_quantity": quantity,
                "frozen_quantity": 0,
                "average_price": 12.34,
                "market_value_cny": quantity * 12.34,
            }
        ],
        orders=[order] if open_order or with_trade else [],
        trades=[trade] if with_trade else [],
        client_version="test",
        gateway_version="test",
    )


def _evidence() -> tuple[AccountSnapshot, BrokerAccountModeLock, PaperAccountBaseline]:
    snapshot = _snapshot()
    lock = build_mode_lock(
        configured_mode="simulation",
        broker_account_matched=True,
        broker_account_type=2,
        broker_account_classification=1,
        broker_account_status=0,
        client_version="test",
        gateway_version="test",
        verified_at=NOW,
    )
    handshake = build_callback_handshake(
        mode_lock=lock,
        snapshot=snapshot,
        subscribed=True,
        unsubscribed=True,
        callback_types=(),
        callback_count=0,
        foreign_account_callback_count=0,
        disconnected=False,
        started_at=NOW,
        completed_at=NOW,
    )
    baseline = build_paper_account_baseline(snapshot, lock, handshake, created_at=NOW)
    return snapshot, lock, baseline


def _authorization(baseline_id: str) -> PaperCanaryAuthorization:
    return build_paper_canary_authorization(
        source_portfolio_target_id="portfolio-target:approved",
        source_shadow_order_plan_id="order-plan:shadow",
        account_baseline_id=baseline_id,
        instrument_id="605208.SH",
        quantity=100,
        max_notional_cny=50_000,
        mandate_start=NOW.replace(hour=9, minute=30),
        mandate_end=NOW.replace(hour=10, minute=0),
        submission_start=NOW.replace(hour=9, minute=35),
        submission_end=NOW.replace(hour=9, minute=45),
        approved_at=NOW - timedelta(days=1),
    )


def _runtime_evidence() -> tuple[
    AccountSnapshot,
    BrokerAccountModeLock,
    PaperAccountBaseline,
    PaperCanaryAuthorization,
    PaperLimitProposal,
    PaperSubmissionApproval,
]:
    snapshot, lock, baseline = _evidence()
    authorization = _authorization(baseline.baseline_id)
    proposal = build_paper_limit_proposal(
        authorization=authorization,
        account_baseline_id=baseline.baseline_id,
        best_ask=12.34,
        quote_market_time=NOW - timedelta(seconds=1),
        quote_received_at=NOW,
    )
    approval = build_submission_approval(
        proposal=proposal,
        authorization=authorization,
        confirmed_limit_price=12.34,
        approved_at=NOW,
        effective_to=NOW + timedelta(minutes=2),
    )
    return snapshot, lock, baseline, authorization, proposal, approval


def test_real_preflight_uses_bound_evidence_and_builds_stable_paper_plan() -> None:
    snapshot, lock, baseline, authorization, proposal, approval = _runtime_evidence()
    preflight = build_real_paper_preflight(
        authorization=authorization,
        proposal=proposal,
        approval=approval,
        mode_lock=lock,
        baseline=baseline,
        account=snapshot,
        quote_market_time=NOW - timedelta(seconds=1),
        quote_received_at=NOW,
        quote_tradable=True,
        now=NOW,
        account_drawdown=0.01,
    )
    assert preflight.evidence_kind == "real_miniqmt"
    assert not preflight.blocker_codes
    first = build_paper_canary_order_plan(
        authorization=authorization,
        approval=approval,
        preflight=preflight,
    )
    second = build_paper_canary_order_plan(
        authorization=authorization,
        approval=approval,
        preflight=preflight,
    )
    assert first == second
    assert str(first.execution_mode) == "paper"


@pytest.mark.parametrize(
    ("cash", "drawdown", "tradable", "blocker"),
    [
        (1_000, 0.01, True, "cash_sufficient"),
        (20_000, 0.08, True, "drawdown_allowed"),
        (20_000, 0.01, False, "tradable"),
    ],
)
def test_real_preflight_fails_closed(
    cash: float, drawdown: float, tradable: bool, blocker: str
) -> None:
    _, lock, baseline, authorization, proposal, approval = _runtime_evidence()
    account = _snapshot(cash=cash)
    baseline = baseline.model_copy(update={"account_snapshot_id": account.account_snapshot_id})
    proposal = proposal.model_copy(update={"account_baseline_id": baseline.baseline_id})
    decision = build_real_paper_preflight(
        authorization=authorization,
        proposal=proposal,
        approval=approval,
        mode_lock=lock,
        baseline=baseline,
        account=account,
        quote_market_time=NOW,
        quote_received_at=NOW,
        quote_tradable=tradable,
        now=NOW,
        account_drawdown=drawdown,
    )
    assert blocker in decision.blocker_codes


def test_approval_must_match_exact_displayed_price_and_short_window() -> None:
    _, _, _, authorization, proposal, _ = _runtime_evidence()
    with pytest.raises(ValueError, match="确切限价"):
        build_submission_approval(
            proposal=proposal,
            authorization=authorization,
            confirmed_limit_price=12.35,
            approved_at=NOW,
            effective_to=NOW + timedelta(minutes=2),
        )
    with pytest.raises(ValueError, match="3分钟"):
        build_submission_approval(
            proposal=proposal,
            authorization=authorization,
            confirmed_limit_price=12.34,
            approved_at=NOW,
            effective_to=NOW + timedelta(minutes=4),
        )


def test_interactive_approval_requires_complete_exact_text(tmp_path: Path) -> None:
    _, _, _, authorization, proposal, _ = _runtime_evidence()
    workflow = PaperCanaryWorkflow(
        Settings(environment="test", shadow_db_path=tmp_path / "paper.sqlite3"),
        clock=lambda: NOW,
    )
    staged = StagedCanary(authorization, proposal)
    expected = "批准 605208.SH 买入100股 限价12.34，仅提交一次"
    assert expected_approval_text(proposal) == expected
    with pytest.raises(ValueError, match="exact_approval_text_mismatch"):
        workflow.approve(staged, "y")
    approval = workflow.approve(staged, expected)
    assert workflow.runtime.approval(approval.approval_id) == approval


def test_workflow_only_waits_when_started_shortly_before_exact_window() -> None:
    _, _, baseline = _evidence()
    authorization = _authorization(baseline.baseline_id)
    assert workflow_start_delay(NOW.replace(hour=9, minute=34), authorization) == 60
    assert workflow_start_delay(NOW, authorization) == 0
    with pytest.raises(ValueError, match="too_early"):
        workflow_start_delay(NOW.replace(hour=9, minute=0), authorization)
    with pytest.raises(ValueError, match="closed"):
        workflow_start_delay(NOW.replace(hour=9, minute=46), authorization)


def test_orchestrator_has_one_submit_site_and_requires_cancel_text() -> None:
    source = (Path(__file__).parents[2] / "scripts/run_paper_canary.py").read_text(encoding="utf-8")
    assert source.count("workflow.submit(") == 1
    assert "workflow.refresh(active)" in source
    assert 'CANCEL_TEXT = "撤销本次金丝雀剩余委托"' in source
    assert "AUTO_CANCEL" not in source


def test_post_close_report_separates_inherited_and_managed_quantity(tmp_path: Path) -> None:
    starting = _snapshot(cash=20_000, quantity=100)
    ending = _snapshot(cash=18_761, quantity=200, with_trade=True)
    projection = PaperOrderProjection(
        projection_id="paper-projection:done",
        intent_id="paper-intent:one",
        idempotency_key="astramind-paper-one",
        state=PaperOrderState.FILLED,
        requested_quantity=100,
        cumulative_filled_quantity=100,
        remaining_quantity=0,
        broker_order_fingerprint=HASH,
        evidence_count=2,
        recovery_required=False,
        updated_at=NOW,
        content_hash=HASH,
    )
    report = build_convergence_report(
        intent_id=projection.intent_id,
        instrument_id="605208.SH",
        starting=starting,
        ending=ending,
        projection=projection,
        created_at=NOW,
    )
    assert report.status == "converged"
    assert report.inherited_quantity == 100
    assert report.managed_quantity == 100
    store = PaperRuntimeStore(tmp_path / "paper.sqlite3")
    store.publish_convergence(report)
    assert store.convergence(report.report_id) == report
