"""Windows-only MiniQMT Paper command runner with one idempotent order remark."""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import hmac
import importlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

GATEWAY_VERSION = "wp-0019-paper-gateway-v1"


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"missing_{name.lower()}")
    return value


def _value(raw: object, name: str, default: object = None) -> object:
    if hasattr(raw, name):
        return getattr(raw, name)
    return raw.get(name, default) if isinstance(raw, dict) else default


def _fingerprint(key: str, *values: object) -> str:
    payload = "\x1f".join(str(value) for value in values).encode()
    return "sha256:" + hmac.new(key.encode(), payload, hashlib.sha256).hexdigest()


def _integer(value: object, *, default: int = 0) -> int:
    if not isinstance(value, str | int | float):
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _number(value: object) -> float:
    if not isinstance(value, str | int | float):
        return 0.0
    try:
        return float(value)
    except ValueError:
        return 0.0


def _matching_account(items: object, selector: str) -> list[object]:
    if not isinstance(items, list | tuple):
        raise RuntimeError("invalid_account_evidence")
    return [item for item in items if str(_value(item, "account_id", "")) == selector]


def _matching_orders(trader: Any, account: object, remark: str) -> list[object]:
    orders = trader.query_stock_orders(account, False)
    if not isinstance(orders, list | tuple):
        raise RuntimeError("order_query_failed")
    return [item for item in orders if str(_value(item, "order_remark", "")) == remark]


def _is_open(order: object) -> bool:
    quantity = _integer(_value(order, "order_volume", 0))
    filled = _integer(_value(order, "traded_volume", 0))
    status = str(_value(order, "order_status", "unknown"))
    return filled < quantity and status not in {
        "53",
        "54",
        "56",
        "57",
        "rejected",
        "canceled",
    }


def _validate_live_quote(config: dict[str, object]) -> None:
    xtdata = importlib.import_module("xtquant.xtdata")
    quote_port = config.get("ASTRAMIND_MINIQMT_QUOTE_PORT")
    if isinstance(quote_port, int):
        xtdata.reconnect(ip="127.0.0.1", port=quote_port)
    instrument = str(config["instrument_id"])
    result = xtdata.get_full_tick([instrument])
    if not isinstance(result, dict) or not isinstance(result.get(instrument), dict):
        raise RuntimeError("full_tick_unavailable")
    tick = result[instrument]
    asks = tick.get("askPrice")
    best_ask = asks[0] if isinstance(asks, list | tuple) and asks else None
    market_time = tick.get("time")
    if not isinstance(best_ask, int | float) or float(best_ask) <= 0:
        raise RuntimeError("best_ask_unavailable")
    if not isinstance(market_time, int | float):
        raise RuntimeError("market_time_unavailable")
    if abs(time.time() - float(market_time) / 1000) > 3:
        raise RuntimeError("quote_stale")
    if float(best_ask) > _number(config.get("limit_price")):
        raise RuntimeError("price_chasing_forbidden")


def _order_result(
    *,
    action: str,
    outcome: str,
    order: object | None,
    key: str,
    selector: str,
) -> dict[str, object]:
    order_id = _value(order, "order_id", "") if order is not None else ""
    filled = _integer(_value(order, "traded_volume", 0)) if order is not None else 0
    price = _number(_value(order, "traded_price", 0)) if order is not None else 0
    return {
        "gateway_version": GATEWAY_VERSION,
        "action": action,
        "outcome": outcome,
        "broker_order_fingerprint": (
            _fingerprint(key, selector, "order", order_id) if order_id else None
        ),
        "broker_status_code": (
            str(_value(order, "order_status", "unknown")) if order is not None else None
        ),
        "cumulative_filled_quantity": max(0, filled),
        "average_fill_price": price if price > 0 else None,
        "observed_at_epoch": time.time(),
    }


def _submit(
    trader: Any,
    account: object,
    config: dict[str, object],
    matches: list[object],
    constants: Any,
    key: str,
    selector: str,
    remark: str,
) -> dict[str, object]:
    if matches:
        return _order_result(
            action="submit", outcome="existing", order=matches[0], key=key, selector=selector
        )
    all_orders = trader.query_stock_orders(account, False)
    if not isinstance(all_orders, list | tuple):
        raise RuntimeError("order_query_failed")
    if any(_is_open(item) for item in all_orders):
        raise RuntimeError("unexpected_open_orders")
    asset = trader.query_stock_asset(account)
    required_cash = _number(config.get("required_cash_cny"))
    if asset is None or _number(_value(asset, "cash", 0)) < required_cash:
        raise RuntimeError("cash_insufficient")
    _validate_live_quote(config)
    side = str(config.get("side"))
    order_type = constants.STOCK_BUY if side == "buy" else constants.STOCK_SELL
    order_id = trader.order_stock(
        account,
        str(config["instrument_id"]),
        order_type,
        _integer(config["quantity"]),
        constants.FIX_PRICE,
        _number(config["limit_price"]),
        "astramind-paper",
        remark,
    )
    if int(order_id) <= 0:
        return _order_result(
            action="submit", outcome="rejected", order=None, key=key, selector=selector
        )
    current = _matching_orders(trader, account, remark)
    order = current[0] if current else {"order_id": order_id}
    return _order_result(
        action="submit", outcome="accepted", order=order, key=key, selector=selector
    )


def _cancel(
    trader: Any,
    account: object,
    matches: list[object],
    key: str,
    selector: str,
) -> dict[str, object]:
    if not matches:
        return _order_result(
            action="cancel", outcome="not_found", order=None, key=key, selector=selector
        )
    result = trader.cancel_order_stock(
        account, _integer(_value(matches[0], "order_id", -1), default=-1)
    )
    outcome = "cancel_requested" if int(result) == 0 else "rejected"
    return _order_result(
        action="cancel", outcome=outcome, order=matches[0], key=key, selector=selector
    )


def run(config: dict[str, object]) -> dict[str, object]:
    selector = _required("ASTRAMIND_MINIQMT_ACCOUNT_ID")
    if _required("ASTRAMIND_MINIQMT_ACCOUNT_MODE") != "simulation":
        raise RuntimeError("simulation_mode_required")
    userdata_path = _required("ASTRAMIND_MINIQMT_USERDATA_PATH")
    key = _required("ASTRAMIND_MINIQMT_FINGERPRINT_KEY")
    xtquant_path = os.environ.get("ASTRAMIND_MINIQMT_XTQUANT_PATH")
    if xtquant_path:
        sys.path.insert(0, xtquant_path)
    constants = importlib.import_module("xtquant.xtconstant")
    trader_module = importlib.import_module("xtquant.xttrader")
    type_module = importlib.import_module("xtquant.xttype")
    account = type_module.StockAccount(selector, "STOCK")
    trader = trader_module.XtQuantTrader(userdata_path, int(time.time_ns() % 2_000_000_000) or 1)
    trader.start()
    subscribed = False
    try:
        if int(trader.connect()) != 0:
            raise RuntimeError("connect_failed")
        if len(_matching_account(trader.query_account_infos(), selector)) != 1:
            raise RuntimeError("account_evidence_not_unique")
        if len(_matching_account(trader.query_account_status(), selector)) != 1:
            raise RuntimeError("account_status_not_unique")
        if int(trader.subscribe(account)) != 0:
            raise RuntimeError("subscribe_failed")
        subscribed = True
        action = str(config.get("action", ""))
        remark = str(config.get("order_remark", ""))
        if not remark or len(remark) > 24:
            raise RuntimeError("invalid_order_remark")
        matches = _matching_orders(trader, account, remark)
        if len(matches) > 1:
            raise RuntimeError("idempotency_conflict")
        if action == "query":
            outcome = "existing" if matches else "not_found"
            return _order_result(
                action=action,
                outcome=outcome,
                order=matches[0] if matches else None,
                key=key,
                selector=selector,
            )
        if action == "submit":
            return _submit(trader, account, config, matches, constants, key, selector, remark)
        if action == "cancel":
            return _cancel(trader, account, matches, key, selector)
        raise RuntimeError("unsupported_action")
    finally:
        if subscribed:
            with contextlib.suppress(Exception):
                trader.unsubscribe(account)
        trader.stop()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    args = parser.parse_args()
    try:
        config = json.loads(Path(args.config).read_text(encoding="utf-8"))
        if not isinstance(config, dict):
            raise RuntimeError("invalid_config")
        for name, value in config.items():
            if isinstance(name, str) and name.startswith("ASTRAMIND_MINIQMT_"):
                os.environ[name] = str(value)
        result = run(config)
    except Exception as error:
        result = {
            "gateway_version": GATEWAY_VERSION,
            "runner_error_code": f"runner_{type(error).__name__.lower()}",
        }
    print(json.dumps(result, ensure_ascii=True, sort_keys=True, separators=(",", ":")))
    return int("runner_error_code" in result)


if __name__ == "__main__":
    raise SystemExit(main())
