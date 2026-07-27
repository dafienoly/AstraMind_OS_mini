"""Windows-only, market-data-only XtQuant probe with bounded subscriptions."""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import importlib
import json
import sys
import threading
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any


def _json_safe(value: object) -> object:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_json_safe(item) for item in value]
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        return _json_safe(to_dict())
    item = getattr(value, "item", None)
    if callable(item):
        return _json_safe(item())
    return repr(value)


def _field_names(payload: object) -> list[str]:
    fields: set[str] = set()
    if isinstance(payload, Mapping):
        fields.update(str(key) for key in payload)
        for value in payload.values():
            if isinstance(value, Mapping):
                fields.update(str(key) for key in value)
    return sorted(fields)


def _row_count(payload: object) -> int:
    if isinstance(payload, (Mapping, Sequence)) and not isinstance(payload, (str, bytes)):
        return len(payload)
    return int(payload is not None)


def _error_code(prefix: str, error: Exception) -> str:
    if isinstance(error, ModuleNotFoundError):
        missing = str(error.name or "unknown").replace(".", "_")
        return f"{prefix}_module_missing_{missing}"
    if "无法连接行情服务" in str(error):
        return f"{prefix}_connection_unavailable"
    return f"{prefix}_{type(error).__name__.lower()}"


def _call(name: str, function: Callable[[], object]) -> tuple[dict[str, object], object | None]:
    try:
        payload = _json_safe(function())
        rows = _row_count(payload)
        return (
            {
                "capability_id": f"miniqmt:{name}",
                "interface_name": name,
                "state": "available" if rows else "empty",
                "interface_present": True,
                "configured": True,
                "permission_available": True,
                "data_available": bool(rows),
                "observed_fields": _field_names(payload),
                "row_count": rows,
            },
            payload,
        )
    except Exception as error:
        return (
            {
                "capability_id": f"miniqmt:{name}",
                "interface_name": name,
                "state": "error",
                "interface_present": True,
                "configured": True,
                "permission_available": None,
                "data_available": False,
                "observed_fields": [],
                "row_count": 0,
                "error_code": _error_code("call", error),
            },
            None,
        )


def _subscription(xtdata: Any, symbol: str, seconds: float) -> tuple[dict[str, object], object]:
    received = threading.Event()
    messages: list[object] = []

    def callback(payload: object) -> None:
        messages.append(_json_safe(payload))
        received.set()

    sequence = -1
    try:
        sequence = int(xtdata.subscribe_quote(symbol, period="tick", callback=callback))
        if sequence < 0:
            raise RuntimeError("subscription_rejected")
        received.wait(seconds)
        state = "available" if messages else "empty"
        return (
            {
                "capability_id": "miniqmt:subscribe_quote",
                "interface_name": "subscribe_quote",
                "state": state,
                "interface_present": True,
                "configured": True,
                "permission_available": True,
                "data_available": bool(messages),
                "observed_fields": _field_names(messages[0]) if messages else [],
                "row_count": len(messages),
                "known_gaps": [] if messages else ["bounded_window_no_message"],
            },
            messages,
        )
    except Exception as error:
        return (
            {
                "capability_id": "miniqmt:subscribe_quote",
                "interface_name": "subscribe_quote",
                "state": "error",
                "interface_present": hasattr(xtdata, "subscribe_quote"),
                "configured": True,
                "permission_available": None,
                "data_available": False,
                "observed_fields": [],
                "row_count": 0,
                "error_code": _error_code("subscription", error),
            },
            messages,
        )
    finally:
        if sequence >= 0:
            with contextlib.suppress(Exception):
                xtdata.unsubscribe_quote(sequence)


def run(
    symbols: list[str],
    subscription_seconds: float,
    xtquant_path: str | None = None,
    quote_port: int | None = None,
) -> dict[str, object]:
    if xtquant_path:
        sys.path.insert(0, xtquant_path)
    package = importlib.import_module("xtquant")
    xtdata = importlib.import_module("xtquant.xtdata")
    if quote_port is not None:
        xtdata.reconnect(ip="127.0.0.1", port=quote_port)
    version = str(getattr(package, "__version__", ""))
    if not version:
        module_file = getattr(xtdata, "__file__", None)
        if isinstance(module_file, str):
            module_bytes = Path(module_file).read_bytes()
            version = "unversioned-sha256-" + hashlib.sha256(module_bytes).hexdigest()[:12]
        else:
            version = "unversioned"
    calls: list[tuple[str, Callable[[], object]]] = [
        ("get_full_tick", lambda: xtdata.get_full_tick(symbols)),
        (
            "get_market_data_ex",
            lambda: xtdata.get_market_data_ex(
                [],
                symbols,
                period="1d",
                count=5,
                dividend_type="none",
                fill_data=False,
            ),
        ),
        ("get_trading_dates", lambda: xtdata.get_trading_dates("SH", count=5)),
        ("get_instrument_detail", lambda: xtdata.get_instrument_detail(symbols[0], False)),
    ]
    capabilities: list[dict[str, object]] = []
    raw_records: list[dict[str, object]] = []
    for name, function in calls:
        capability, payload = _call(name, function)
        capabilities.append(capability)
        if payload is not None:
            raw_records.append({"interface_name": name, "payload": payload})
    capability, payload = _subscription(xtdata, symbols[0], subscription_seconds)
    capabilities.append(capability)
    raw_records.append({"interface_name": "subscribe_quote", "payload": payload})
    capabilities.append(
        {
            "capability_id": "miniqmt:l2",
            "interface_name": "get_l2_quote",
            "state": "not_probed",
            "interface_present": hasattr(xtdata, "get_l2_quote"),
            "configured": True,
            "permission_available": None,
            "data_available": False,
            "observed_fields": [],
            "row_count": 0,
            "known_gaps": ["l2_default_disabled"],
        }
    )
    return {
        "gateway_version": "wp-0002a-windows-runner-v1",
        "client_version": version,
        "capabilities": capabilities,
        "raw_records": raw_records,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbols", default="000001.SH,399001.SZ")
    parser.add_argument("--subscription-seconds", type=float, default=3.0)
    parser.add_argument("--xtquant-path")
    parser.add_argument("--quote-port", type=int)
    args = parser.parse_args()
    try:
        result = run(
            args.symbols.split(","),
            args.subscription_seconds,
            args.xtquant_path,
            args.quote_port,
        )
    except ModuleNotFoundError as error:
        missing = str(error.name or "unknown").replace(".", "_")
        result = {
            "gateway_version": "wp-0002a-windows-runner-v1",
            "client_version": "unavailable",
            "capabilities": [],
            "raw_records": [],
            "runner_error_code": f"runner_module_missing_{missing}",
        }
    except Exception as error:
        result = {
            "gateway_version": "wp-0002a-windows-runner-v1",
            "client_version": "unavailable",
            "capabilities": [],
            "raw_records": [],
            "runner_error_code": f"runner_{type(error).__name__.lower()}",
        }
    print(json.dumps(result, ensure_ascii=True, separators=(",", ":")))
    return int("runner_error_code" in result)


if __name__ == "__main__":
    raise SystemExit(main())
