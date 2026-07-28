from __future__ import annotations

import asyncio
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from astramind_mini.trading_execution.adapters import (
    FilesystemAccountReconciliationStore,
)
from astramind_mini.trading_execution.adapters.miniqmt_account import (
    MiniQMTAccountClient,
    MiniQMTAccountError,
    build_account_snapshot,
)
from astramind_mini.trading_execution.application import StartupReconciliationService
from astramind_mini.trading_execution.contracts.account import (
    AccountPosition,
    AccountSnapshot,
    ReconciliationReport,
)
from astramind_mini.trading_execution.domain import (
    reconcile_account,
    synthetic_shadow_projection,
)

HASH_A = "sha256:" + "a" * 64
NOW = datetime(2026, 7, 28, 1, 0, tzinfo=UTC)


def _snapshot(
    *,
    positions: Sequence[object] | None = None,
    orders: Sequence[object] | None = None,
) -> AccountSnapshot:
    return build_account_snapshot(
        account_mode="simulation",
        account_fingerprint=HASH_A,
        as_of=NOW,
        asset={
            "cash_cny": 50_000.0,
            "frozen_cash_cny": 0.0,
            "market_value_cny": 0.0,
            "total_asset_cny": 50_000.0,
        },
        positions=list(positions or []),
        orders=list(orders or []),
        trades=[],
        client_version="xtquant-test",
        gateway_version="wp-0011-test",
    )


def test_account_snapshot_is_strict_private_and_order_independent() -> None:
    positions = [
        {
            "instrument_id": "000002.SZ",
            "quantity": 200,
            "available_quantity": 100,
            "frozen_quantity": 0,
            "average_price": 12.5,
            "market_value_cny": 2_500.0,
        },
        {
            "instrument_id": "000001.SZ",
            "quantity": 100,
            "available_quantity": 100,
            "frozen_quantity": 0,
            "average_price": 10.0,
            "market_value_cny": 1_000.0,
        },
    ]
    first = _snapshot(positions=positions)
    second = _snapshot(positions=list(reversed(positions)))

    assert first == second
    assert [item.instrument_id for item in first.positions] == ["000001.SZ", "000002.SZ"]
    serialized = first.model_dump_json()
    assert "account_id" not in serialized
    assert "userdata" not in serialized
    with pytest.raises(ValidationError):
        AccountPosition.model_validate(
            {
                **positions[0],
                "available_quantity": 300,
                "secret": "forbidden",
            }
        )
    with pytest.raises(ValidationError):
        first.account_mode = "live"


def test_reconciliation_matches_or_blocks_without_authorizing_broker_actions() -> None:
    snapshot = _snapshot()
    matched = reconcile_account(
        synthetic_shadow_projection(as_of=NOW),
        snapshot,
        created_at=NOW,
    )
    assert matched.status == "matched"
    assert matched.blocker_codes == ()
    assert matched.broker_actions_allowed is False

    position = AccountPosition(
        instrument_id="000001.SZ",
        quantity=100,
        available_quantity=100,
        frozen_quantity=0,
        average_price=10,
        market_value_cny=1_000,
    )
    blocked = reconcile_account(
        synthetic_shadow_projection(as_of=NOW, cash_cny=49_000),
        _snapshot(positions=[position.model_dump(mode="json")]),
        created_at=NOW,
    )
    assert blocked.status == "blocked"
    assert blocked.blocker_codes == ("cash_difference", "position_difference")
    assert blocked.broker_actions_allowed is False


def test_account_store_is_wal_append_only_and_restart_safe(tmp_path: Path) -> None:
    database = tmp_path / "shadow.sqlite3"
    root = tmp_path / "evidence"
    store = FilesystemAccountReconciliationStore(root=root, database=database)
    snapshot = _snapshot()
    report = reconcile_account(
        synthetic_shadow_projection(as_of=NOW),
        snapshot,
        created_at=NOW,
    )

    snapshot_path = store.publish_account_snapshot(snapshot)
    report_path = store.publish_reconciliation(report)
    restarted = FilesystemAccountReconciliationStore(root=root, database=database)
    assert restarted.publish_account_snapshot(snapshot) == snapshot_path
    assert restarted.publish_reconciliation(report) == report_path
    assert restarted.publication_counts() == (1, 1)
    assert restarted.journal_mode().lower() == "wal"

    snapshot_path.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="身份发生内容冲突"):
        restarted.publish_account_snapshot(snapshot)


def test_partial_query_failure_cannot_build_snapshot() -> None:
    class FailingReader:
        async def read(self) -> AccountSnapshot:
            raise MiniQMTAccountError("orders_timeout")

    class RejectingStore:
        def publish_account_snapshot(self, snapshot: AccountSnapshot) -> Path:
            raise AssertionError("部分成功不得发布")

        def publish_reconciliation(self, report: ReconciliationReport) -> Path:
            raise AssertionError("部分成功不得发布")

    async def run() -> None:
        service = StartupReconciliationService(
            reader=FailingReader(),
            store=RejectingStore(),
        )
        await service.run(
            synthetic_shadow_projection(as_of=NOW),
            created_at=NOW,
        )

    with pytest.raises(MiniQMTAccountError, match="orders_timeout"):
        asyncio.run(run())


def test_account_client_requires_all_four_queries(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = MiniQMTAccountClient(
        runner=tmp_path / "runner.py",
        python_command=None,
        xtquant_path=None,
        userdata_path="secret-userdata",
        account_selector="account-placeholder",
        account_mode="simulation",
        fingerprint_key="secret-key",
    )
    called: list[str] = []

    async def invoke(interface: str) -> dict[str, object]:
        called.append(interface)
        if interface == "orders":
            raise MiniQMTAccountError("orders_timeout")
        return {
            "interface": interface,
            "account_mode": "simulation",
            "account_fingerprint": HASH_A,
            "client_version": "test",
            "gateway_version": "test",
            "data": {} if interface == "asset" else [],
        }

    monkeypatch.setattr(client, "_invoke", invoke)
    with pytest.raises(MiniQMTAccountError, match="orders_timeout"):
        asyncio.run(client.read())
    assert called == ["asset", "positions", "orders"]


def test_runner_source_has_no_broker_write_or_callback_surface() -> None:
    source = Path("scripts/miniqmt_account_runner.py").read_text(encoding="utf-8").lower()
    forbidden = (
        ".order_stock(",
        ".order_stock_async(",
        ".cancel_order_stock(",
        ".cancel_order_stock_async(",
        "register_callback",
        ".subscribe(",
        "on_stock_order",
        "on_stock_trade",
    )
    assert all(token not in source for token in forbidden)
    assert all(
        query in source
        for query in (
            "query_stock_asset",
            "query_stock_positions",
            "query_stock_orders",
            "query_stock_trades",
        )
    )
