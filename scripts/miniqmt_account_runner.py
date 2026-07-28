"""Windows-only MiniQMT account query runner with no broker write surface."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import importlib
import json
import os
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

INTERFACES = ("asset", "positions", "orders", "trades")
GATEWAY_VERSION = "wp-0011-readonly-account-runner-v1"


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


def _normalize_order(
    raw: object,
    *,
    account_selector: str,
    key: str,
    constants: Any,
) -> dict[str, object]:
    order_id = _value(raw, "order_id", "order_sysid", default="")
    quantity = _integer(_value(raw, "order_volume"))
    filled = _integer(_value(raw, "traded_volume"))
    status = str(_value(raw, "order_status", "status", default="unknown"))
    return {
        "order_fingerprint": _fingerprint(key, account_selector, "order", order_id),
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


def _normalize_trade(
    raw: object,
    *,
    account_selector: str,
    key: str,
    constants: Any,
) -> dict[str, object]:
    order_id = _value(raw, "order_id", "order_sysid", default="")
    trade_id = _value(raw, "traded_id", "trade_id", default="")
    quantity = _integer(_value(raw, "traded_volume"))
    price = _number(_value(raw, "traded_price"))
    return {
        "trade_fingerprint": _fingerprint(key, account_selector, "trade", trade_id),
        "order_fingerprint": _fingerprint(key, account_selector, "order", order_id),
        "instrument_id": str(_value(raw, "stock_code", default="")),
        "side": _side(_value(raw, "order_type"), constants),
        "quantity": quantity,
        "price": price,
        "amount_cny": _number(_value(raw, "traded_amount", default=quantity * price)),
        "occurred_at": _value(raw, "traded_time", default=None),
    }


def run(interface: str) -> dict[str, object]:
    if interface not in INTERFACES:
        raise RuntimeError("unsupported_interface")
    account_selector = _required("ASTRAMIND_MINIQMT_ACCOUNT_ID")
    account_mode = _required("ASTRAMIND_MINIQMT_ACCOUNT_MODE")
    userdata_path = _required("ASTRAMIND_MINIQMT_USERDATA_PATH")
    fingerprint_key = _required("ASTRAMIND_MINIQMT_FINGERPRINT_KEY")
    xtquant_path = os.environ.get("ASTRAMIND_MINIQMT_XTQUANT_PATH")
    if xtquant_path:
        sys.path.insert(0, xtquant_path)
    package = importlib.import_module("xtquant")
    constants = importlib.import_module("xtquant.xtconstant")
    trader_module = importlib.import_module("xtquant.xttrader")
    type_module = importlib.import_module("xtquant.xttype")
    account = type_module.StockAccount(account_selector, "STOCK")
    session_id = int(os.environ.get("ASTRAMIND_MINIQMT_SESSION_ID", "0") or 0)
    if session_id <= 0:
        session_id = int(time.time_ns() % 2_000_000_000)
    trader = trader_module.XtQuantTrader(userdata_path, session_id)
    trader.start()
    try:
        result = trader.connect()
        if int(result) != 0:
            raise RuntimeError(f"connect_error_{result}")
        queries: dict[str, Callable[[], object]] = {
            "asset": lambda: trader.query_stock_asset(account),
            "positions": lambda: trader.query_stock_positions(account),
            "orders": lambda: trader.query_stock_orders(account, False),
            "trades": lambda: trader.query_stock_trades(account),
        }
        raw = queries[interface]()
        if raw is None:
            raise RuntimeError(f"{interface}_empty_response")
        if interface == "asset":
            data: object = _normalize_asset(raw)
        elif not isinstance(raw, list | tuple):
            raise RuntimeError(f"{interface}_invalid_response")
        elif interface == "positions":
            data = [_normalize_position(item) for item in raw]
        elif interface == "orders":
            data = [
                _normalize_order(
                    item,
                    account_selector=account_selector,
                    key=fingerprint_key,
                    constants=constants,
                )
                for item in raw
            ]
        else:
            data = [
                _normalize_trade(
                    item,
                    account_selector=account_selector,
                    key=fingerprint_key,
                    constants=constants,
                )
                for item in raw
            ]
        return {
            "interface": interface,
            "account_mode": account_mode,
            "account_fingerprint": _fingerprint(
                fingerprint_key, account_selector, account_mode, "account"
            ),
            "client_version": str(getattr(package, "__version__", "unknown")),
            "gateway_version": GATEWAY_VERSION,
            "data": data,
        }
    finally:
        trader.stop()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--interface", choices=INTERFACES, required=True)
    parser.add_argument("--config", required=True)
    args = parser.parse_args()
    try:
        config = json.loads(Path(args.config).read_text(encoding="utf-8"))
        if not isinstance(config, dict):
            raise RuntimeError("invalid_config")
        for name in (
            "ASTRAMIND_MINIQMT_ACCOUNT_ID",
            "ASTRAMIND_MINIQMT_ACCOUNT_MODE",
            "ASTRAMIND_MINIQMT_USERDATA_PATH",
            "ASTRAMIND_MINIQMT_FINGERPRINT_KEY",
            "ASTRAMIND_MINIQMT_SESSION_ID",
            "ASTRAMIND_MINIQMT_XTQUANT_PATH",
        ):
            value = config.get(name)
            if value is not None:
                os.environ[name] = str(value)
        result = run(args.interface)
    except Exception as error:
        result = {
            "interface": args.interface,
            "gateway_version": GATEWAY_VERSION,
            "runner_error_code": f"runner_{type(error).__name__.lower()}",
        }
    print(json.dumps(result, ensure_ascii=True, sort_keys=True, separators=(",", ":")))
    return int("runner_error_code" in result)


if __name__ == "__main__":
    raise SystemExit(main())
