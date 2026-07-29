"""Windows-only single-instrument MiniQMT L1 quote reader."""

from __future__ import annotations

import argparse
import importlib
import json
import sys
import time
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any
from zoneinfo import ZoneInfo


def _first_positive(value: object) -> float:
    if isinstance(value, list | tuple) and value:
        value = value[0]
    if isinstance(value, int | float) and float(value) > 0:
        return float(value)
    raise RuntimeError("best_ask_unavailable")


def _instrument_detail(xtdata: Any, instrument: str) -> dict[str, object]:
    getter = xtdata.get_instrument_detail
    try:
        value = getter(instrument, False)
    except TypeError:
        value = getter(instrument)
    if not isinstance(value, dict):
        raise RuntimeError("instrument_detail_unavailable")
    return value


def _listed_long_enough(value: object, market_time_ms: int) -> bool:
    text = str(value or "").replace("-", "")[:8]
    if len(text) != 8 or not text.isdigit():
        return False
    listed = datetime.strptime(text, "%Y%m%d").date()
    market_date = datetime.fromtimestamp(market_time_ms / 1000, tz=ZoneInfo("Asia/Shanghai")).date()
    return (market_date - listed).days >= 10


def _limit_up(last_close: float) -> float:
    return float(
        (Decimal(str(last_close)) * Decimal("1.10")).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
    )


def _read_tick(xtdata: Any, instrument: str) -> dict[str, object]:
    result = xtdata.get_full_tick([instrument])
    if not isinstance(result, dict) or instrument not in result:
        raise RuntimeError("full_tick_unavailable")
    tick = result[instrument]
    if not isinstance(tick, dict):
        raise RuntimeError("invalid_full_tick")
    return tick


def run(
    instrument: str,
    xtquant_path: str | None,
    quote_port: int | None,
    fresh_wait_seconds: float,
) -> dict[str, object]:
    if xtquant_path:
        sys.path.insert(0, xtquant_path)
    xtdata = importlib.import_module("xtquant.xtdata")
    if quote_port is not None:
        xtdata.reconnect(ip="127.0.0.1", port=quote_port)
    deadline = time.monotonic() + fresh_wait_seconds
    first_market_time_ms: int | None = None
    sample_count = 0
    while True:
        tick = _read_tick(xtdata, instrument)
        sample_count += 1
        market_time = tick.get("time")
        if not isinstance(market_time, int | float) or market_time <= 0:
            raise RuntimeError("market_time_unavailable")
        market_time_ms = int(market_time)
        first_market_time_ms = first_market_time_ms or market_time_ms
        age_seconds = time.time() - market_time_ms / 1000
        if 0 <= age_seconds <= 3:
            break
        if time.monotonic() >= deadline:
            return {
                "gateway_version": "wp-0022-canary-quote-v3",
                "runner_error_code": "quote_stale",
                "sample_count": sample_count,
                "new_tick_observed": market_time_ms != first_market_time_ms,
            }
        time.sleep(min(0.25, max(deadline - time.monotonic(), 0)))
    best_ask = _first_positive(tick.get("askPrice"))
    last_close = _first_positive(tick.get("lastClose"))
    detail = _instrument_detail(xtdata, instrument)
    instrument_name = str(detail.get("InstrumentName", "")).upper()
    risk_warning = "ST" in instrument_name or "退" in instrument_name
    listed_long_enough = _listed_long_enough(detail.get("OpenDate"), market_time_ms)
    limit_up = _limit_up(last_close)
    return {
        "gateway_version": "wp-0022-canary-quote-v3",
        "instrument_id": instrument,
        "best_ask": best_ask,
        "last_close": last_close,
        "limit_up": limit_up,
        "risk_warning": risk_warning,
        "listed_long_enough": listed_long_enough,
        "instrument_detail_available": True,
        "market_time_ms": market_time_ms,
        "sample_count": sample_count,
        "new_tick_observed": market_time_ms != first_market_time_ms,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--instrument", required=True)
    parser.add_argument("--xtquant-path")
    parser.add_argument("--quote-port", type=int)
    parser.add_argument("--fresh-wait-seconds", type=float, default=8.0)
    args = parser.parse_args()
    try:
        result = run(
            args.instrument,
            args.xtquant_path,
            args.quote_port,
            max(0.0, args.fresh_wait_seconds),
        )
    except Exception as error:
        message = str(error).lower()
        disconnected = any(
            marker in message
            for marker in (
                "not connected",
                "connect failed",
                "connection refused",
                "未连接",
                "连接失败",
            )
        )
        result = {
            "gateway_version": "wp-0022-canary-quote-v3",
            "runner_error_code": (
                "qmt_not_connected" if disconnected else f"runner_{type(error).__name__.lower()}"
            ),
        }
    print(json.dumps(result, ensure_ascii=True, sort_keys=True, separators=(",", ":")))
    return int("runner_error_code" in result)


if __name__ == "__main__":
    raise SystemExit(main())
