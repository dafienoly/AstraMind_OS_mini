"""Windows-only bounded MiniQMT L1 full-push capture."""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import importlib
import json
import sys
import threading
from collections.abc import Mapping, Sequence
from pathlib import Path


def _safe(value: object) -> object:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Mapping):
        return {str(key): _safe(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_safe(item) for item in value]
    item = getattr(value, "item", None)
    return _safe(item()) if callable(item) else repr(value)


def capture(
    markets: list[str],
    seconds: float,
    xtquant_path: str | None,
    quote_port: int | None,
) -> dict[str, object]:
    if xtquant_path:
        sys.path.insert(0, xtquant_path)
    package = importlib.import_module("xtquant")
    xtdata = importlib.import_module("xtquant.xtdata")
    if quote_port is not None:
        xtdata.reconnect(ip="127.0.0.1", port=quote_port)
    if not hasattr(xtdata, "subscribe_whole_quote"):
        raise RuntimeError("whole_quote_interface_missing")
    messages: list[object] = []
    bounded_window = threading.Event()

    def callback(payload: object) -> None:
        messages.append(_safe(payload))

    sequence = -1
    unsubscribed = False
    try:
        sequence = int(xtdata.subscribe_whole_quote(markets, callback=callback))
        if sequence < 0:
            raise RuntimeError("whole_quote_subscription_rejected")
        bounded_window.wait(seconds)
    finally:
        if sequence >= 0:
            with contextlib.suppress(Exception):
                xtdata.unsubscribe_quote(sequence)
                unsubscribed = True
    version = str(getattr(package, "__version__", ""))
    module_file = getattr(xtdata, "__file__", None)
    if not version and isinstance(module_file, str):
        version = (
            "unversioned-sha256-" + hashlib.sha256(Path(module_file).read_bytes()).hexdigest()[:12]
        )
    return {
        "gateway_version": "wp-0002c-l1-runner-v1",
        "client_version": version or "unversioned",
        "markets": markets,
        "messages": messages,
        "subscribed": sequence >= 0,
        "unsubscribed": unsubscribed,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--markets", default="SH,SZ,BJ")
    parser.add_argument("--seconds", type=float, default=5)
    parser.add_argument("--xtquant-path")
    parser.add_argument("--quote-port", type=int)
    args = parser.parse_args()
    try:
        result = capture(
            args.markets.split(","),
            args.seconds,
            args.xtquant_path,
            args.quote_port,
        )
    except Exception as error:
        result = {
            "gateway_version": "wp-0002c-l1-runner-v1",
            "client_version": "unavailable",
            "runner_error_code": f"runner_{type(error).__name__.lower()}",
        }
    print(json.dumps(result, ensure_ascii=True, separators=(",", ":")))
    return int("runner_error_code" in result)


if __name__ == "__main__":
    raise SystemExit(main())
