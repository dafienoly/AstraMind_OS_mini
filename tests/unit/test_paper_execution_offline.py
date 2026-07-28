from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from astramind_mini.contracts import ExecutionEvent, ExecutionMode, OrderPlan
from astramind_mini.trading_execution.adapters import (
    OfflinePaperGateway,
    PaperExecutionStore,
)
from astramind_mini.trading_execution.application import OfflinePaperExecutionService
from astramind_mini.trading_execution.contracts.paper import (
    PaperBrokerObservation,
    PaperObservationKind,
    PaperOrderIntent,
    PaperPreflightDecision,
)
from astramind_mini.trading_execution.domain import (
    build_paper_intent,
    build_paper_preflight,
    canonical_hash,
)

NOW = datetime(2026, 7, 28, 9, 31, tzinfo=UTC)
HASH_A = "sha256:" + "a" * 64


def _preflight(**overrides: bool) -> PaperPreflightDecision:
    checks = {
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
    }
    checks.update(overrides)
    return build_paper_preflight(created_at=NOW, checks=checks)


def _plan(mode: ExecutionMode = ExecutionMode.PAPER) -> OrderPlan:
    return OrderPlan(
        order_plan_id="order-plan:test-paper",
        portfolio_target_id="portfolio-target:test",
        standing_mandate_id=None,
        execution_mode=mode,
        created_at=NOW,
        content_hash=HASH_A,
    )


def _intent() -> PaperOrderIntent:
    return build_paper_intent(
        order_plan=_plan(),
        line_id="line:1",
        instrument_id="000001.SZ",
        side="buy",
        quantity=200,
        limit_price=10.25,
        preflight=_preflight(),
        created_at=NOW,
    )


def _observation(
    intent: PaperOrderIntent,
    kind: PaperObservationKind,
    *,
    sequence: int,
    filled: int = 0,
    received_offset: int = 0,
    suffix: str | None = None,
) -> PaperBrokerObservation:
    marker = suffix or f"{kind}-{sequence}-{filled}"
    occurred_at = NOW + timedelta(seconds=received_offset)
    event_hash = canonical_hash({"marker": marker, "event": True})
    event = ExecutionEvent(
        execution_event_id=f"paper-event:{marker}",
        order_plan_id=intent.order_plan.order_plan_id,
        execution_mode=ExecutionMode.PAPER,
        event_type=f"paper_{kind}",
        sequence=sequence,
        occurred_at=occurred_at,
        content_hash=event_hash,
    )
    content_hash = canonical_hash({"marker": marker, "evidence": True})
    return PaperBrokerObservation(
        evidence_id=f"paper-evidence:{marker}",
        intent_id=intent.intent_id,
        idempotency_key=intent.idempotency_key,
        execution_event=event,
        kind=kind,
        broker_sequence=sequence,
        cumulative_filled_quantity=filled,
        average_fill_price=10.2 if filled else None,
        broker_order_fingerprint=HASH_A,
        source="synthetic_offline",
        received_at=occurred_at,
        content_hash=content_hash,
    )


def test_contracts_are_strict_frozen_and_paper_only() -> None:
    preflight = _preflight()
    with pytest.raises(ValidationError):
        preflight.model_copy(update={"unknown": True}).__class__.model_validate(
            {**preflight.model_dump(), "unknown": True}
        )
    with pytest.raises(ValidationError):
        preflight.account_mode_verified = False
    with pytest.raises(ValueError, match="execution_mode=paper"):
        build_paper_intent(
            order_plan=_plan(ExecutionMode.SHADOW),
            line_id="line:1",
            instrument_id="000001.SZ",
            side="buy",
            quantity=100,
            limit_price=10,
            preflight=preflight,
            created_at=NOW,
        )


def test_preflight_and_limit_lot_rules_fail_closed() -> None:
    assert _preflight(quote_fresh=False).blocker_codes == ("quote_fresh",)
    with pytest.raises(ValueError, match="存在阻断"):
        build_paper_intent(
            order_plan=_plan(),
            line_id="line:1",
            instrument_id="000001.SZ",
            side="buy",
            quantity=100,
            limit_price=10,
            preflight=_preflight(quote_fresh=False),
            created_at=NOW,
        )
    with pytest.raises(ValidationError, match="100 股整数手"):
        build_paper_intent(
            order_plan=_plan(),
            line_id="line:1",
            instrument_id="000001.SZ",
            side="buy",
            quantity=150,
            limit_price=10,
            preflight=_preflight(),
            created_at=NOW,
        )


def test_intent_and_idempotency_key_are_deterministic() -> None:
    assert _intent() == _intent()
    assert _intent().idempotency_key.startswith("astramind-paper-")
    assert _intent().broker_actions_allowed is False


def test_duplicate_and_out_of_order_observations_do_not_regress(tmp_path: Path) -> None:
    intent = _intent()
    store = PaperExecutionStore(tmp_path / "paper.sqlite3")
    service = OfflinePaperExecutionService(store, OfflinePaperGateway())
    service.prepare(intent)
    partial = _observation(
        intent,
        PaperObservationKind.PARTIAL_FILL,
        sequence=2,
        filled=100,
        received_offset=2,
    )
    assert service.record(intent, partial).state == "partially_filled"
    assert service.record(intent, partial).evidence_count == 1
    late_ack = _observation(
        intent,
        PaperObservationKind.ACKNOWLEDGED,
        sequence=1,
        received_offset=3,
    )
    projection = service.record(intent, late_ack)
    assert projection.state == "partially_filled"
    assert projection.cumulative_filled_quantity == 100
    assert projection.evidence_count == 2


def test_unknown_recovery_queries_facts_and_never_submits(tmp_path: Path) -> None:
    intent = _intent()
    unknown = _observation(intent, PaperObservationKind.SUBMISSION_UNKNOWN, sequence=1)
    ack = _observation(
        intent,
        PaperObservationKind.ACKNOWLEDGED,
        sequence=2,
        received_offset=1,
    )
    gateway = OfflinePaperGateway((ack,))
    store = PaperExecutionStore(tmp_path / "paper.sqlite3")
    service = OfflinePaperExecutionService(store, gateway)
    service.prepare(intent)
    uncertain = service.record(intent, unknown)
    assert uncertain.recovery_required is True
    assert uncertain.retry_permitted is False

    recovered = service.recover_unknown(intent)
    assert recovered.state == "acknowledged"
    assert recovered.recovery_required is False
    assert gateway.lookup_count == 1
    assert gateway.command_attempt_count == 0


def test_cancel_fill_race_converges_to_filled(tmp_path: Path) -> None:
    intent = _intent()
    store = PaperExecutionStore(tmp_path / "paper.sqlite3")
    service = OfflinePaperExecutionService(store, OfflinePaperGateway())
    service.prepare(intent)
    pending = service.record(
        intent,
        _observation(intent, PaperObservationKind.CANCEL_REQUESTED, sequence=2),
    )
    assert pending.state == "cancel_pending"
    filled = service.record(
        intent,
        _observation(
            intent,
            PaperObservationKind.FILLED,
            sequence=3,
            filled=200,
            received_offset=1,
        ),
    )
    assert filled.state == "filled"
    assert filled.remaining_quantity == 0


def test_impossible_fill_and_terminal_conflict_are_rejected(tmp_path: Path) -> None:
    intent = _intent()
    store = PaperExecutionStore(tmp_path / "paper.sqlite3")
    service = OfflinePaperExecutionService(store, OfflinePaperGateway())
    service.prepare(intent)
    with pytest.raises(ValueError, match="超过委托数量"):
        service.record(
            intent,
            _observation(
                intent,
                PaperObservationKind.FILLED,
                sequence=1,
                filled=300,
            ),
        )
    rejected = _observation(intent, PaperObservationKind.REJECTED, sequence=2)
    assert service.record(intent, rejected).state == "rejected"
    with pytest.raises(ValueError, match="矛盾证据"):
        service.record(
            intent,
            _observation(intent, PaperObservationKind.ACKNOWLEDGED, sequence=3),
        )


def test_store_is_append_only_wal_and_restart_safe(tmp_path: Path) -> None:
    intent = _intent()
    database = tmp_path / "paper.sqlite3"
    store = PaperExecutionStore(database)
    service = OfflinePaperExecutionService(store, OfflinePaperGateway())
    service.prepare(intent)
    ack = _observation(intent, PaperObservationKind.ACKNOWLEDGED, sequence=1)
    expected = service.record(intent, ack)

    restarted = PaperExecutionStore(database)
    assert restarted.read_intent(intent.intent_id) == intent
    assert restarted.observations_for(intent.intent_id) == (ack,)
    assert restarted.latest_projection(intent.intent_id) == expected
    assert restarted.counts() == (1, 1, 2)
    assert restarted.journal_mode().lower() == "wal"

    conflict = ack.model_copy(update={"content_hash": canonical_hash("conflict")})
    with pytest.raises(ValueError, match="身份发生内容冲突"):
        restarted.append_observation(conflict)


def test_offline_gateway_rejects_all_command_attempts() -> None:
    gateway = OfflinePaperGateway()
    with pytest.raises(PermissionError, match="写入未授权"):
        gateway.send_limit_intent(_intent())
    with pytest.raises(PermissionError, match="撤单未授权"):
        gateway.request_cancel(_intent())
    assert gateway.command_attempt_count == 2


def test_wp0016_sources_have_no_broker_sdk_or_local_account_material() -> None:
    root = Path(__file__).parents[2] / "src/astramind_mini/trading_execution"
    files = (
        root / "contracts/paper.py",
        root / "domain/paper.py",
        root / "ports/paper.py",
        root / "adapters/offline_paper.py",
        root / "adapters/paper_store.py",
        root / "application/paper.py",
    )
    forbidden = (
        "xt" + "quant",
        "XtQuant" + "Trader",
        "order_" + "stock",
        "cancel_order_" + "stock",
        "userdata_" + "path",
        "account_" + "id",
    )
    content = "\n".join(path.read_text(encoding="utf-8") for path in files)
    assert not any(term in content for term in forbidden)
