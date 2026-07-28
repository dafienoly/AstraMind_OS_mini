from __future__ import annotations

import asyncio
import importlib.util
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from astramind_mini.trading_execution.adapters import (
    FilesystemAccountReconciliationStore,
    MiniQMTAccountError,
    MiniQMTPaperReadonlyClient,
    PaperStartupStore,
)
from astramind_mini.trading_execution.adapters.miniqmt_account_normalization import (
    build_account_snapshot,
)
from astramind_mini.trading_execution.application import PaperStartupService
from astramind_mini.trading_execution.contracts.account import AccountSnapshot
from astramind_mini.trading_execution.contracts.paper_startup import PaperStartupEvidence
from astramind_mini.trading_execution.domain import (
    build_callback_handshake,
    build_mode_lock,
    build_paper_account_baseline,
)

NOW = datetime(2026, 7, 28, 4, 0, tzinfo=UTC)
HASH_A = "sha256:" + "a" * 64
ACCOUNT_PLACEHOLDER = "account-placeholder"


def _snapshot(*, open_order: bool = False) -> AccountSnapshot:
    orders: list[object] = (
        [
            {
                "order_fingerprint": HASH_A,
                "instrument_id": "000002.SZ",
                "side": "buy",
                "status": "submitted",
                "quantity": 100,
                "filled_quantity": 0,
                "price": 10.0,
                "occurred_at": NOW,
                "is_open": True,
            }
        ]
        if open_order
        else []
    )
    return build_account_snapshot(
        account_mode="simulation",
        account_fingerprint=HASH_A,
        as_of=NOW,
        asset={
            "cash_cny": 20_000.0,
            "frozen_cash_cny": 0.0,
            "market_value_cny": 1_000.0,
            "total_asset_cny": 21_000.0,
        },
        positions=[
            {
                "instrument_id": "000001.SZ",
                "quantity": 100,
                "available_quantity": 100,
                "frozen_quantity": 0,
                "average_price": 10.0,
                "market_value_cny": 1_000.0,
            }
        ],
        orders=orders,
        trades=[],
        client_version="test",
        gateway_version="wp-0017-test",
    )


def _evidence(*, open_order: bool = False, callback_count: int = 1) -> PaperStartupEvidence:
    snapshot = _snapshot(open_order=open_order)
    lock = build_mode_lock(
        configured_mode="simulation",
        broker_account_matched=True,
        broker_account_type=2,
        broker_account_classification=1,
        broker_account_status=0,
        client_version="test",
        gateway_version="wp-0017-test",
        verified_at=NOW,
    )
    handshake = build_callback_handshake(
        mode_lock=lock,
        snapshot=snapshot,
        subscribed=True,
        unsubscribed=True,
        callback_types=("account_status",) if callback_count else (),
        callback_count=callback_count,
        foreign_account_callback_count=0,
        disconnected=False,
        started_at=NOW,
        completed_at=NOW,
    )
    baseline = build_paper_account_baseline(snapshot, lock, handshake, created_at=NOW)
    return PaperStartupEvidence(
        mode_lock=lock,
        account_snapshot=snapshot,
        callback_handshake=handshake,
        account_baseline=baseline,
    )


@pytest.mark.parametrize(
    ("configured_mode", "matched", "classification", "status"),
    [
        ("live", True, 1, 0),
        ("simulation", False, 1, 0),
        ("simulation", True, 1, 3),
    ],
)
def test_mode_lock_fails_closed(
    configured_mode: str,
    matched: bool,
    classification: int | None,
    status: int,
) -> None:
    with pytest.raises(ValueError):
        build_mode_lock(
            configured_mode=configured_mode,
            broker_account_matched=matched,
            broker_account_type=2,
            broker_account_classification=classification,
            broker_account_status=status,
            client_version="test",
            gateway_version="test",
            verified_at=NOW,
        )


def test_quiet_callback_window_is_evidence_not_failure() -> None:
    evidence = _evidence(callback_count=0)
    assert evidence.callback_handshake.status == "quiet"
    assert evidence.callback_handshake.subscribed is True
    assert evidence.callback_handshake.unsubscribed is True
    assert evidence.account_baseline.new_orders_frozen is True
    assert evidence.account_baseline.broker_actions_allowed is False


def test_missing_optional_account_classification_is_disclosed() -> None:
    lock = build_mode_lock(
        configured_mode="simulation",
        broker_account_matched=True,
        broker_account_type=2,
        broker_account_classification=None,
        broker_account_status=0,
        client_version="test",
        gateway_version="test",
        verified_at=NOW,
    )
    assert lock.known_gaps == ("account_classification_not_returned",)
    assert lock.mode_evidence == "configured_simulation_selector_matched"


def test_inherited_positions_and_open_orders_enter_complete_baseline() -> None:
    evidence = _evidence(open_order=True)
    baseline = evidence.account_baseline
    assert baseline.authority == "complete_miniqmt_simulation_account"
    assert baseline.inherited_instrument_ids == ("000001.SZ",)
    assert baseline.managed_position_count == 0
    assert baseline.open_order_fingerprints == (HASH_A,)
    assert "preexisting_open_orders" in baseline.blocker_codes
    assert baseline.startup_state == "blocked"


def test_handshake_rejects_foreign_account_or_incomplete_cleanup() -> None:
    evidence = _evidence()
    with pytest.raises(ValueError, match="非目标账户"):
        build_callback_handshake(
            mode_lock=evidence.mode_lock,
            snapshot=evidence.account_snapshot,
            subscribed=True,
            unsubscribed=True,
            callback_types=("trade",),
            callback_count=1,
            foreign_account_callback_count=1,
            disconnected=False,
            started_at=NOW,
            completed_at=NOW,
        )
    with pytest.raises(ValueError, match="生命周期不完整"):
        build_callback_handshake(
            mode_lock=evidence.mode_lock,
            snapshot=evidence.account_snapshot,
            subscribed=True,
            unsubscribed=False,
            callback_types=(),
            callback_count=0,
            foreign_account_callback_count=0,
            disconnected=False,
            started_at=NOW,
            completed_at=NOW,
        )


def test_client_rejects_live_before_starting_runner(tmp_path: Path) -> None:
    client = MiniQMTPaperReadonlyClient(
        runner=tmp_path / "runner.py",
        python_command=None,
        xtquant_path=None,
        userdata_path="private",
        account_selector="private",
        account_mode="live",
        fingerprint_key="private",
    )
    with pytest.raises(MiniQMTAccountError, match="simulation_mode_required"):
        asyncio.run(client.read())


def test_service_publishes_append_only_restart_safe_evidence(tmp_path: Path) -> None:
    evidence = _evidence()

    class Reader:
        async def read(self) -> PaperStartupEvidence:
            return evidence

    database = tmp_path / "shadow.sqlite3"
    account_store = FilesystemAccountReconciliationStore(
        root=tmp_path / "accounts",
        database=database,
    )
    startup_store = PaperStartupStore(database)
    service = PaperStartupService(
        reader=Reader(),
        account_store=account_store,
        startup_store=startup_store,
    )
    first = asyncio.run(service.run())
    second = asyncio.run(service.run())

    assert first == second
    restarted = PaperStartupStore(database)
    assert restarted.read_baseline(evidence.account_baseline.baseline_id) == (
        evidence.account_baseline
    )
    assert restarted.counts() == (1, 1, 1)
    assert restarted.journal_mode().lower() == "wal"
    conflict = evidence.account_baseline.model_copy(update={"content_hash": "sha256:" + "b" * 64})
    with pytest.raises(ValueError, match="身份发生内容冲突"):
        restarted.publish_baseline(conflict)


def test_windows_runner_unsubscribes_and_stops(monkeypatch: pytest.MonkeyPatch) -> None:
    path = Path("scripts/miniqmt_paper_readonly_runner.py")
    spec = importlib.util.spec_from_file_location("paper_readonly_runner_test", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    state = {"unsubscribed": 0, "stopped": 0}

    class CallbackBase:
        pass

    class Trader:
        def __init__(self, *_: object) -> None:
            self.callback: Any = None

        def register_callback(self, callback: object) -> None:
            self.callback = callback

        def start(self) -> None:
            pass

        def connect(self) -> int:
            return 0

        def query_account_infos(self) -> list[object]:
            return [
                SimpleNamespace(
                    account_type=2,
                    account_classification=1,
                    **{"account_id": ACCOUNT_PLACEHOLDER},
                )
            ]

        def query_account_status(self) -> list[object]:
            return [SimpleNamespace(status=0, **{"account_id": ACCOUNT_PLACEHOLDER})]

        def subscribe(self, account: object) -> int:
            assert self.callback is not None
            self.callback.on_account_status(SimpleNamespace(**{"account_id": ACCOUNT_PLACEHOLDER}))
            return 0

        def query_stock_asset(self, account: object) -> object:
            return SimpleNamespace(cash=1, frozen_cash=0, market_value=0, total_asset=1)

        def query_stock_positions(self, account: object) -> list[object]:
            return []

        def query_stock_orders(self, account: object, cancelable: bool) -> list[object]:
            return []

        def query_stock_trades(self, account: object) -> list[object]:
            return []

        def unsubscribe(self, account: object) -> int:
            state["unsubscribed"] += 1
            return 0

        def stop(self) -> None:
            state["stopped"] += 1

    modules = {
        "xtquant": SimpleNamespace(__version__="test"),
        "xtquant.xtconstant": SimpleNamespace(STOCK_BUY=23, STOCK_SELL=24),
        "xtquant.xttrader": SimpleNamespace(
            XtQuantTrader=Trader,
            XtQuantTraderCallback=CallbackBase,
        ),
        "xtquant.xttype": SimpleNamespace(
            StockAccount=lambda selector, kind: SimpleNamespace(**{"account_id": selector})
        ),
    }
    monkeypatch.setattr(module.importlib, "import_module", modules.__getitem__)
    monkeypatch.setenv("ASTRAMIND_MINIQMT_ACCOUNT_ID", ACCOUNT_PLACEHOLDER)
    monkeypatch.setenv("ASTRAMIND_MINIQMT_ACCOUNT_MODE", "simulation")
    monkeypatch.setenv("ASTRAMIND_MINIQMT_USERDATA_PATH", "private")
    monkeypatch.setenv("ASTRAMIND_MINIQMT_FINGERPRINT_KEY", "private")
    monkeypatch.setenv("ASTRAMIND_MINIQMT_CALLBACK_WAIT_SECONDS", "0")

    result = module.run()
    assert result["subscribed"] is True
    assert result["unsubscribed"] is True
    assert result["callback_count"] == 1
    assert state == {"unsubscribed": 1, "stopped": 1}

    monkeypatch.setattr(Trader, "query_stock_asset", lambda *_: None)
    with pytest.raises(RuntimeError, match="incomplete_account_baseline"):
        module.run()
    assert state == {"unsubscribed": 2, "stopped": 2}


def test_runner_has_no_order_or_cancel_command_surface() -> None:
    source = Path("scripts/miniqmt_paper_readonly_runner.py").read_text(encoding="utf-8")
    forbidden = (
        ".order_" + "stock(",
        ".order_" + "stock_async(",
        ".cancel_order_" + "stock(",
        ".cancel_order_" + "stock_async(",
    )
    assert all(token not in source for token in forbidden)
    assert "query_account_infos" in source
    assert "query_account_status" in source
    assert "register_callback" in source
    assert ".subscribe(" in source
    assert ".unsubscribe(" in source
