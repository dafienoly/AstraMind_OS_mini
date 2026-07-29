"""Probe all in-scope read-only MiniQMT data capabilities and preserve raw evidence."""

from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path
from time import monotonic

from astramind_mini.config import Settings
from astramind_mini.data.adapters import (
    FilesystemRawRecordStore,
    MiniQMTBridgeClient,
    MiniQMTSourceAdapter,
)
from astramind_mini.data.application.identity import canonical_json, content_hash
from astramind_mini.data.contracts import CanonicalDatasetRequest, RawRecordEnvelope

ROOT = Path(__file__).resolve().parents[1]
UNSUPPORTED = (
    "l2_order_book",
    "transaction_orders",
    "transaction_trades",
    "northbound_flow",
    "etf_iopv_redemption",
    "announcement_qa",
    "ipo",
)


def requests(as_of: datetime, instrument: str, index: str) -> tuple[CanonicalDatasetRequest, ...]:
    end = as_of.date()
    start = end - timedelta(days=31)
    extended_start = end - timedelta(days=365 * 5)

    def bounded(
        dataset_name: str,
        *,
        universe: tuple[str, ...] = (),
        fields: tuple[str, ...] = (),
        filters: dict[str, str | int | bool | tuple[str, ...]] | None = None,
        frequency: str = "1d",
        use_extended_window: bool = False,
    ) -> CanonicalDatasetRequest:
        return CanonicalDatasetRequest(
            dataset_name=dataset_name,
            as_of=as_of,
            start_date=extended_start if use_extended_window else start,
            end_date=end,
            universe=universe,
            fields=fields,
            filters=filters or {},
            frequency=frequency,
        )

    return (
        bounded(
            "daily_market",
            universe=(instrument,),
            fields=("instrument_id", "trade_date", "open", "close", "volume", "amount"),
        ),
        bounded(
            "broad_index_daily",
            universe=(index,),
            fields=("instrument_id", "trade_date", "open", "close", "volume", "amount"),
        ),
        bounded(
            "minute_market",
            universe=(instrument,),
            frequency="1m",
            fields=("instrument_id", "time", "open", "close", "volume", "amount"),
        ),
        CanonicalDatasetRequest(
            dataset_name="instrument_snapshot",
            as_of=as_of,
            universe=(instrument,),
        ),
        bounded(
            "trade_calendar_check",
            filters={"market": "SH"},
        ),
        CanonicalDatasetRequest(
            dataset_name="index_constituent_weight_current",
            as_of=as_of,
            universe=(index,),
        ),
        CanonicalDatasetRequest(dataset_name="sector_catalog_current", as_of=as_of),
        CanonicalDatasetRequest(
            dataset_name="sector_membership_current",
            as_of=as_of,
            filters={"sectors": ("沪深300", "上证50", "中证500")},
        ),
        *(
            bounded(
                "financial_statement",
                universe=(instrument,),
                filters={"table": table, "download": True},
                use_extended_window=True,
            )
            for table in ("Balance", "Income", "CashFlow", "PershareIndex", "Capital")
        ),
        bounded(
            "shareholder_count",
            universe=(instrument,),
            filters={"download": True},
            use_extended_window=True,
        ),
        bounded(
            "top10_holder",
            universe=(instrument,),
            filters={"download": True},
            use_extended_window=True,
        ),
        bounded(
            "top10_float_holder",
            universe=(instrument,),
            filters={"download": True},
            use_extended_window=True,
        ),
        bounded(
            "corporate_action_factor",
            universe=(instrument,),
            use_extended_window=True,
        ),
    )


async def run(args: argparse.Namespace) -> int:
    settings = Settings()
    if settings.miniqmt_xtquant_path is None or settings.miniqmt_quote_port is None:
        raise ValueError("必须固定 MiniQMT XtQuant 路径和只读行情端口")
    bridge = MiniQMTBridgeClient(
        runner=ROOT / "scripts/windows/miniqmt_data_bridge.py",
        xtquant_path=settings.miniqmt_xtquant_path,
        quote_port=settings.miniqmt_quote_port,
        python_command=settings.miniqmt_python or "py",
    )
    raw_store = FilesystemRawRecordStore(settings.data_dir / "provider-raw")
    results = []
    await bridge.start()
    try:
        adapter = MiniQMTSourceAdapter(bridge)
        for request in requests(datetime.now(UTC), args.instrument, args.index):
            started = monotonic()
            try:
                batch = await adapter.fetch(request)
                raw_store.append(
                    RawRecordEnvelope(
                        provider=batch.provider_id,
                        interface_name=batch.native_interface,
                        source_endpoint=batch.source_endpoint,
                        request_identity=batch.request_identity,
                        received_at=batch.retrieved_at,
                        schema_version="miniqmt-catalog-probe-v1",
                        content_hash=content_hash(batch.raw_payload),
                    ),
                    batch.raw_payload,
                )
                fields = sorted({field for row in batch.rows for field in row})
                result = {
                    "dataset_name": request.dataset_name,
                    "filters": request.filters,
                    "state": "available" if batch.rows else "empty",
                    "rows": len(batch.rows),
                    "fields": fields,
                    "latency_ms": (monotonic() - started) * 1000,
                    "request_identity": batch.request_identity,
                }
            except Exception as error:
                result = {
                    "dataset_name": request.dataset_name,
                    "filters": request.filters,
                    "state": "error",
                    "rows": 0,
                    "fields": [],
                    "latency_ms": (monotonic() - started) * 1000,
                    "error_code": getattr(error, "code", type(error).__name__.lower()),
                }
            results.append(result)
    finally:
        await bridge.stop()
    report = {
        "schema_version": "miniqmt-catalog-probe-v1",
        "probed_at": datetime.now(UTC),
        "provider_version": bridge.provider_version,
        "client_fingerprint": bridge.client_fingerprint,
        "results": results,
        "unsupported": UNSUPPORTED,
        "broker_actions_allowed": False,
    }
    identity = content_hash(report)
    output = settings.data_dir / "probes" / identity.rsplit(":", 1)[-1] / "report.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(canonical_json(report))
    print(f"probe_id={identity}")
    print(f"datasets={len(results)}")
    print(f"report={output}")
    print("broker_actions_allowed=false")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--instrument", default="600519.SH")
    parser.add_argument("--index", default="000300.SH")
    return asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
