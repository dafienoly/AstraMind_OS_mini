"""Windows-only persistent MiniQMT session for WP-0017 read-only evidence."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import importlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

GATEWAY_VERSION = "wp-0017-paper-readonly-handshake-v1"


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"missing_{name.lower()}")
    return value


def _value(raw: object, *names: str, default: object = None) -> object:
    for name in names:
        if hasattr(raw, name):
            return getattr(raw, name)
        if isinstance(raw, dict) and name in raw:
            return raw[name]
    return default


def _number(value: object) -> float:
    try:
        if not isinstance(value, str | int | float):
            return 0.0
        return max(0.0, float(value or 0))
    except (TypeError, ValueError):
        return 0.0


def _integer(value: object) -> int:
    try:
        if not isinstance(value, str | int | float):
            return 0
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _signed_integer(value: object, *, default: int = -999) -> int:
    try:
        if not isinstance(value, str | int | float):
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _optional_signed_integer(value: object) -> int | None:
    if value is None:
        return None
    result = _signed_integer(value)
    return None if result == -999 else result


def _fingerprint(key: str, *values: object) -> str:
    payload = "\x1f".join(str(value) for value in values).encode("utf-8")
    return "sha256:" + hmac.new(key.encode("utf-8"), payload, hashlib.sha256).hexdigest()


def _side(value: object, constants: Any) -> str:
    if value == getattr(constants, "STOCK_BUY", object()):
        return "buy"
    if value == getattr(constants, "STOCK_SELL", object()):
        return "sell"
    return "unknown"


def _normalize_asset(raw: object) -> dict[str, object]:
    return {
        "cash_cny": _number(_value(raw, "cash")),
        "frozen_cash_cny": _number(_value(raw, "frozen_cash")),
        "market_value_cny": _number(_value(raw, "market_value")),
        "total_asset_cny": _number(_value(raw, "total_asset")),
    }


def _normalize_position(raw: object) -> dict[str, object]:
    return {
        "instrument_id": str(_value(raw, "stock_code", default="")),
        "quantity": _integer(_value(raw, "volume")),
        "available_quantity": _integer(_value(raw, "can_use_volume")),
        "frozen_quantity": _integer(_value(raw, "frozen_volume")),
        "average_price": _number(_value(raw, "avg_price", "open_price")),
        "market_value_cny": _number(_value(raw, "market_value")),
    }


def _normalize_order(raw: object, selector: str, key: str, constants: Any) -> dict[str, object]:
    order_id = _value(raw, "order_id", "order_sysid", default="")
    quantity = _integer(_value(raw, "order_volume"))
    filled = _integer(_value(raw, "traded_volume"))
    status = str(_value(raw, "order_status", "status", default="unknown"))
    return {
        "order_fingerprint": _fingerprint(key, selector, "order", order_id),
        "instrument_id": str(_value(raw, "stock_code", default="")),
        "side": _side(_value(raw, "order_type"), constants),
        "status": status,
        "quantity": quantity,
        "filled_quantity": filled,
        "price": _number(_value(raw, "price", "order_price")),
        "occurred_at": _value(raw, "order_time", default=None),
        "is_open": filled < quantity
        and status not in {"53", "54", "56", "57", "rejected", "canceled"},
    }


def _normalize_trade(raw: object, selector: str, key: str, constants: Any) -> dict[str, object]:
    order_id = _value(raw, "order_id", "order_sysid", default="")
    trade_id = _value(raw, "traded_id", "trade_id", default="")
    quantity = _integer(_value(raw, "traded_volume"))
    price = _number(_value(raw, "traded_price"))
    return {
        "trade_fingerprint": _fingerprint(key, selector, "trade", trade_id),
        "order_fingerprint": _fingerprint(key, selector, "order", order_id),
        "instrument_id": str(_value(raw, "stock_code", default="")),
        "side": _side(_value(raw, "order_type"), constants),
        "quantity": quantity,
        "price": price,
        "amount_cny": _number(_value(raw, "traded_amount", default=quantity * price)),
        "occurred_at": _value(raw, "traded_time", default=None),
    }


class CallbackEvidence:
    def __init__(self, selector: str) -> None:
        self._selector = selector
        self.types: list[str] = []
        self.foreign_count = 0
        self.disconnected = False

    def record(self, kind: str, value: object | None = None) -> None:
        observed_selector = _value(value, "account_id", default=None) if value is not None else None
        if observed_selector not in {None, "", self._selector}:
            self.foreign_count += 1
            return
        self.types.append(kind)


def _callback(callback_base: type[Any], evidence: CallbackEvidence) -> object:
    class ReadonlyCallback(callback_base):  # type: ignore[misc]
        def on_disconnected(self) -> None:
            evidence.disconnected = True
            evidence.record("disconnected")

        def on_account_status(self, status: object) -> None:
            evidence.record("account_status", status)

        def on_stock_asset(self, asset: object) -> None:
            evidence.record("asset", asset)

        def on_stock_position(self, position: object) -> None:
            evidence.record("position", position)

        def on_stock_order(self, order: object) -> None:
            evidence.record("order", order)

        def on_stock_trade(self, trade: object) -> None:
            evidence.record("trade", trade)

    return ReadonlyCallback()


def _matching(items: object, selector: str) -> list[object]:
    if not isinstance(items, list | tuple):
        raise RuntimeError("invalid_account_evidence")
    return [item for item in items if str(_value(item, "account_id", default="")) == selector]


def run() -> dict[str, object]:
    selector = _required("ASTRAMIND_MINIQMT_ACCOUNT_ID")
    mode = _required("ASTRAMIND_MINIQMT_ACCOUNT_MODE")
    if mode != "simulation":
        raise RuntimeError("simulation_mode_required")
    userdata_path = _required("ASTRAMIND_MINIQMT_USERDATA_PATH")
    fingerprint_key = _required("ASTRAMIND_MINIQMT_FINGERPRINT_KEY")
    wait_seconds = float(os.environ.get("ASTRAMIND_MINIQMT_CALLBACK_WAIT_SECONDS", "2"))
    xtquant_path = os.environ.get("ASTRAMIND_MINIQMT_XTQUANT_PATH")
    if xtquant_path:
        sys.path.insert(0, xtquant_path)
    package = importlib.import_module("xtquant")
    constants = importlib.import_module("xtquant.xtconstant")
    trader_module = importlib.import_module("xtquant.xttrader")
    type_module = importlib.import_module("xtquant.xttype")
    account = type_module.StockAccount(selector, "STOCK")
    evidence = CallbackEvidence(selector)
    callback = _callback(trader_module.XtQuantTraderCallback, evidence)
    session_id = int(time.time_ns() % 2_000_000_000) or 1
    trader = trader_module.XtQuantTrader(userdata_path, session_id)
    trader.register_callback(callback)
    trader.start()
    subscribed = False
    unsubscribed = False
    started_at = time.time()
    try:
        if int(trader.connect()) != 0:
            raise RuntimeError("connect_failed")
        infos = _matching(trader.query_account_infos(), selector)
        statuses = _matching(trader.query_account_status(), selector)
        if len(infos) != 1 or len(statuses) != 1:
            raise RuntimeError("account_evidence_not_unique")
        info, account_status = infos[0], statuses[0]
        if int(trader.subscribe(account)) != 0:
            raise RuntimeError("subscribe_failed")
        subscribed = True
        asset = trader.query_stock_asset(account)
        positions = trader.query_stock_positions(account)
        orders = trader.query_stock_orders(account, False)
        trades = trader.query_stock_trades(account)
        if asset is None or not isinstance(positions, list | tuple):
            raise RuntimeError("incomplete_account_baseline")
        if not isinstance(orders, list | tuple) or not isinstance(trades, list | tuple):
            raise RuntimeError("incomplete_account_baseline")
        deadline = time.monotonic() + max(0.0, min(wait_seconds, 10.0))
        while time.monotonic() < deadline:
            time.sleep(0.05)
        result: dict[str, object] = {
            "account_mode": mode,
            "account_matched": True,
            "account_fingerprint": _fingerprint(fingerprint_key, selector, mode, "account"),
            "account_type": _signed_integer(_value(info, "account_type")),
            "account_classification": _optional_signed_integer(
                _value(info, "account_classification")
            ),
            "account_status": _signed_integer(_value(account_status, "status")),
            "client_version": str(getattr(package, "__version__", "unknown")),
            "gateway_version": GATEWAY_VERSION,
            "asset": _normalize_asset(asset),
            "positions": [_normalize_position(item) for item in positions],
            "orders": [
                _normalize_order(item, selector, fingerprint_key, constants) for item in orders
            ],
            "trades": [
                _normalize_trade(item, selector, fingerprint_key, constants) for item in trades
            ],
            "callback_types": evidence.types,
            "callback_count": len(evidence.types),
            "foreign_account_callback_count": evidence.foreign_count,
            "disconnected": evidence.disconnected,
            "started_at_epoch": started_at,
        }
        return result
    finally:
        if subscribed:
            try:
                unsubscribed = int(trader.unsubscribe(account)) == 0
            except Exception:
                unsubscribed = False
        trader.stop()
        if "result" in locals():
            result["subscribed"] = subscribed
            result["unsubscribed"] = unsubscribed
            result["completed_at_epoch"] = time.time()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    args = parser.parse_args()
    try:
        config = json.loads(Path(args.config).read_text(encoding="utf-8"))
        if not isinstance(config, dict):
            raise RuntimeError("invalid_config")
        for name, value in config.items():
            if (
                isinstance(name, str)
                and name.startswith("ASTRAMIND_MINIQMT_")
                and value is not None
            ):
                os.environ[name] = str(value)
        result = run()
    except Exception as error:
        result = {
            "gateway_version": GATEWAY_VERSION,
            "runner_error_code": f"runner_{type(error).__name__.lower()}",
        }
    print(json.dumps(result, ensure_ascii=True, sort_keys=True, separators=(",", ":")))
    return int("runner_error_code" in result)


if __name__ == "__main__":
    raise SystemExit(main())
