"""Long-lived, Windows-only, read-only XtQuant market-data bridge."""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import importlib
import json
import os
import sys
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from miniqmt_bridge_payloads import (  # type: ignore[import-not-found]
    financial_rows as _financial_rows,
)
from miniqmt_bridge_payloads import (
    json_safe as _json_safe,
)
from miniqmt_bridge_payloads import (
    mapping as _mapping,
)
from miniqmt_bridge_payloads import (
    market_matrix_rows as _market_matrix_rows,
)
from miniqmt_bridge_payloads import (
    market_rows as _market_rows,
)
from miniqmt_bridge_payloads import (
    nested_rows as _nested_rows,
)
from miniqmt_bridge_payloads import strings as _strings

ALLOWED_DATASETS = {
    "daily_market",
    "broad_index_daily",
    "minute_market",
    "instrument_snapshot",
    "trade_calendar_check",
    "index_constituent_weight_current",
    "sector_membership_current",
    "sector_catalog_current",
    "financial_statement",
    "shareholder_count",
    "top10_holder",
    "top10_float_holder",
    "corporate_action_factor",
}


class Bridge:
    def __init__(self, xtdata: Any, version: str, quote_port: int) -> None:
        self.xtdata = xtdata
        self.version = version
        self.client_fingerprint = hashlib.sha256(
            f"{version}:127.0.0.1:{quote_port}".encode()
        ).hexdigest()
        self.sequence = -1
        self.write_lock = threading.Lock()
        self.latest: dict[str, object] = {}

    def handle(self, request: dict[str, object]) -> bool:
        request_id = str(request.get("request_id", ""))
        command = str(request.get("command", ""))
        if command == "shutdown":
            self.unsubscribe()
            self.send({"type": "response", "request_id": request_id, "ok": True})
            return False
        try:
            result: dict[str, object]
            if command == "health":
                result = {
                    "provider_version": self.version,
                    "client_fingerprint": self.client_fingerprint,
                    "state": "healthy",
                }
            elif command == "fetch":
                result = self.fetch(_mapping(request.get("request")))
            elif command == "prepare_history_cache":
                result = self.prepare_history_cache(
                    list(_strings(request.get("universe"))),
                    period=str(request.get("period", "1d")),
                    start_time=str(request.get("start_time", "")),
                    end_time=str(request.get("end_time", "")),
                )
            elif command == "subscribe":
                result = self.subscribe(_strings(request.get("markets")))
            elif command == "unsubscribe":
                result = self.unsubscribe()
            elif command == "snapshot":
                result = {"rows": list(self.latest.values())}
            else:
                raise ValueError("unsupported_command")
            self.send(
                {
                    "type": "response",
                    "request_id": request_id,
                    "ok": True,
                    "result": result,
                }
            )
        except Exception as error:
            self.send(
                {
                    "type": "response",
                    "request_id": request_id,
                    "ok": False,
                    "error_code": _error_code(error),
                }
            )
        return True

    def prepare_history_cache(
        self,
        universe: list[str],
        *,
        period: str,
        start_time: str,
        end_time: str,
    ) -> dict[str, object]:
        if not universe:
            raise ValueError("empty_universe")
        if period not in {"1d", "1m"}:
            raise ValueError("unsupported_period")
        started = datetime.now(UTC)
        result = self.xtdata.download_history_data2(
            universe,
            period,
            start_time=start_time,
            end_time=end_time,
            incrementally=False,
        )
        ended = datetime.now(UTC)
        return {
            "provider_version": self.version,
            "native_interface": "download_history_data2",
            "instrument_count": len(universe),
            "result_count": len(_mapping(result)),
            "started_at": started.isoformat(),
            "ended_at": ended.isoformat(),
            "elapsed_ms": (ended - started).total_seconds() * 1000,
        }

    def fetch(self, request: dict[str, object]) -> dict[str, object]:
        dataset = str(request.get("dataset_name", ""))
        if dataset not in ALLOWED_DATASETS:
            raise ValueError("unsupported_dataset")
        universe = list(_strings(request.get("universe")))
        filters = _mapping(request.get("filters"))
        started = datetime.now(UTC)
        resolved_all_market = dataset == "daily_market" and not universe
        if resolved_all_market:
            universe = list(self.xtdata.get_stock_list_in_sector("沪深京A股"))
        if dataset in {"daily_market", "broad_index_daily", "minute_market"}:
            rows, payload, interface = self._fetch_market(dataset, request, universe, filters)
            if resolved_all_market:
                payload = {"resolved_universe": universe, "market_data": payload}
                interface = "get_stock_list_in_sector+get_market_data"
        elif dataset == "instrument_snapshot":
            rows = [
                {"instrument_id": item, **_mapping(self.xtdata.get_instrument_detail(item, True))}
                for item in universe
            ]
            payload, interface = rows, "get_instrument_detail"
        elif dataset == "trade_calendar_check":
            market = str(filters.get("market", "SH"))
            payload = self.xtdata.get_trading_dates(
                market,
                start_time=str(filters.get("start_time", "")),
                end_time=str(filters.get("end_time", "")),
                count=int(str(filters.get("count", -1))),
            )
            rows = [{"market": market, "market_time": value} for value in payload]
            interface = "get_trading_dates"
        elif dataset == "index_constituent_weight_current":
            rows = []
            weight_payload: dict[str, object] = {}
            if bool(filters.get("download", False)):
                self.xtdata.download_index_weight()
            for instrument in universe:
                value = self.xtdata.get_index_weight(instrument)
                weight_payload[instrument] = value
                rows.extend(
                    {
                        "index_id": instrument,
                        "instrument_id": str(symbol),
                        "weight": weight,
                    }
                    for symbol, weight in _mapping(value).items()
                )
            payload, interface = weight_payload, "get_index_weight"
        elif dataset == "sector_catalog_current":
            if bool(filters.get("download", False)):
                self.xtdata.download_sector_data()
            payload = self.xtdata.get_sector_list()
            prefixes = _strings(filters.get("prefixes"))
            rows = [
                {"sector_name": str(sector)}
                for sector in payload
                if not prefixes or str(sector).startswith(prefixes)
            ]
            interface = "get_sector_list"
        elif dataset == "sector_membership_current":
            sectors = list(_strings(filters.get("sectors")))
            rows = [
                {"sector_name": sector, "instrument_id": instrument}
                for sector in sectors
                for instrument in self.xtdata.get_stock_list_in_sector(sector)
            ]
            payload, interface = rows, "get_stock_list_in_sector"
        elif dataset in {
            "financial_statement",
            "shareholder_count",
            "top10_holder",
            "top10_float_holder",
        }:
            rows, payload, interface = self._fetch_financial(dataset, universe, filters)
        else:
            payload = {
                instrument: self.xtdata.get_divid_factors(
                    instrument,
                    start_time=str(filters.get("start_time", "")),
                    end_time=str(filters.get("end_time", "")),
                )
                for instrument in universe
            }
            rows = _nested_rows(payload, "instrument_id")
            interface = "get_divid_factors"
        ended = datetime.now(UTC)
        return {
            "provider_version": self.version,
            "native_interface": interface,
            "retrieved_at": ended.isoformat(),
            "rows": _json_safe(rows),
            "raw_payload": _json_safe(payload),
            "latency_breakdown_ms": {"provider": (ended - started).total_seconds() * 1000},
        }

    def _fetch_market(
        self,
        dataset: str,
        request: dict[str, object],
        universe: list[str],
        filters: dict[str, object],
    ) -> tuple[list[dict[str, object]], object, str]:
        period = "1m" if dataset == "minute_market" else str(request.get("frequency", "1d"))
        if bool(filters.get("download", False)):
            self.xtdata.download_history_data2(
                universe,
                period,
                start_time=str(filters.get("start_time", "")),
                end_time=str(filters.get("end_time", "")),
                incrementally=False,
            )
        arguments = {
            "stock_list": universe,
            "period": period,
            "start_time": str(filters.get("start_time", "")),
            "end_time": str(filters.get("end_time", "")),
            "count": int(str(filters.get("count", -1))),
            "dividend_type": str(request.get("adjustment", "none")),
            "fill_data": False,
        }
        if bool(filters.get("matrix", False)):
            payload = self.xtdata.get_market_data(
                [
                    "time",
                    "open",
                    "high",
                    "low",
                    "close",
                    "preClose",
                    "volume",
                    "amount",
                ],
                **arguments,
            )
            return _market_matrix_rows(payload), payload, "get_market_data"
        payload = self.xtdata.get_market_data_ex([], **arguments)
        return _market_rows(payload), payload, "get_market_data_ex"

    def _fetch_financial(
        self,
        dataset: str,
        universe: list[str],
        filters: dict[str, object],
    ) -> tuple[list[dict[str, object]], object, str]:
        table = {
            "financial_statement": str(filters.get("table", "Balance")),
            "shareholder_count": "HolderNum",
            "top10_holder": "Top10Holder",
            "top10_float_holder": "Top10FlowHolder",
        }[dataset]
        if bool(filters.get("download", False)):
            self.xtdata.download_financial_data(
                universe,
                [table],
                start_time=str(filters.get("start_time", "")),
                end_time=str(filters.get("end_time", "")),
            )
        payload = self.xtdata.get_financial_data(
            universe,
            [table],
            start_time=str(filters.get("start_time", "")),
            end_time=str(filters.get("end_time", "")),
            report_type=str(filters.get("report_type", "report_time")),
        )
        return _financial_rows(payload, table), payload, "get_financial_data"

    def subscribe(self, markets: tuple[str, ...]) -> dict[str, object]:
        if self.sequence >= 0:
            raise RuntimeError("already_subscribed")

        def callback(payload: object) -> None:
            received_at = datetime.now(UTC).isoformat()
            safe = _json_safe(payload)
            if isinstance(safe, dict):
                for instrument, quote in safe.items():
                    self.latest[str(instrument)] = {
                        "instrument_id": str(instrument),
                        "received_at": received_at,
                        "quote": quote,
                    }
            self.send(
                {
                    "type": "event",
                    "event": "quote",
                    "received_at": received_at,
                    "payload": safe,
                }
            )

        self.sequence = int(self.xtdata.subscribe_whole_quote(list(markets), callback=callback))
        if self.sequence < 0:
            raise RuntimeError("subscription_rejected")
        return {"sequence": self.sequence, "markets": list(markets)}

    def unsubscribe(self) -> dict[str, object]:
        sequence = self.sequence
        if sequence >= 0:
            with contextlib.suppress(Exception):
                self.xtdata.unsubscribe_quote(sequence)
        self.sequence = -1
        return {"sequence": sequence, "unsubscribed": sequence >= 0}

    def send(self, payload: dict[str, object]) -> None:
        body = json.dumps(payload, ensure_ascii=True, separators=(",", ":"), default=str)
        with self.write_lock:
            sys.stdout.write(body + "\n")
            sys.stdout.flush()


def _error_code(error: Exception) -> str:
    text = str(error)
    if "无法连接行情服务" in text:
        return "quote_service_unavailable"
    return f"{type(error).__name__.lower()}:{text[:120]}"


def _version(package: object, xtdata: object) -> str:
    value = str(getattr(package, "__version__", ""))
    if value:
        return value
    module_file = getattr(xtdata, "__file__", None)
    if isinstance(module_file, str):
        digest = hashlib.sha256(Path(module_file).read_bytes()).hexdigest()[:12]
        return "unversioned-" + digest
    return "unversioned"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--xtquant-path")
    parser.add_argument("--quote-port", type=int, required=True)
    args = parser.parse_args()
    if args.xtquant_path:
        sys.path.insert(0, args.xtquant_path)
    package = importlib.import_module("xtquant")
    xtdata = importlib.import_module("xtquant.xtdata")
    xtdata.reconnect(ip="127.0.0.1", port=args.quote_port)
    bridge = Bridge(xtdata, _version(package, xtdata), args.quote_port)
    bridge.send(
        {
            "type": "ready",
            "provider_version": bridge.version,
            "client_fingerprint": bridge.client_fingerprint,
            "process_id": os.getpid(),
        }
    )
    for line in sys.stdin:
        with contextlib.suppress(json.JSONDecodeError):
            value = json.loads(line)
            if isinstance(value, dict) and not bridge.handle(value):
                break
    bridge.unsubscribe()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
