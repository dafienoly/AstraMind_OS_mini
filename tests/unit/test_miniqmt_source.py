from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime

from astramind_mini.data.adapters.miniqmt_source import MiniQMTSourceAdapter
from astramind_mini.data.contracts.source import CanonicalDatasetRequest


class RecordingBridge:
    provider_version = "test"
    client_fingerprint = "fingerprint"

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []
        self.fetch_count = 0

    async def request(
        self,
        command: str,
        *,
        timeout_seconds: float = 30,
        **payload: object,
    ) -> dict[str, object]:
        self.calls.append((command, {"timeout_seconds": timeout_seconds, **payload}))
        if command == "prepare_history_cache":
            return {
                "native_interface": "download_history_data2",
                "started_at": "2026-07-30T08:00:00+00:00",
                "ended_at": "2026-07-30T08:00:01+00:00",
            }
        self.fetch_count += 1
        trade_day = 29 if self.fetch_count == 1 else 30
        return {
            "provider_version": "test",
            "native_interface": "get_market_data",
            "retrieved_at": "2026-07-30T08:00:02+00:00",
            "rows": [
                {
                    "instrument_id": "000001.SH",
                    "time": datetime(
                        2026,
                        7,
                        trade_day,
                        tzinfo=UTC,
                    ).timestamp()
                    * 1000,
                    "open": 1,
                    "high": 2,
                    "low": 1,
                    "close": 2,
                    "volume": 3,
                    "amount": 4,
                }
            ],
            "raw_payload": {"test": True},
            "latency_breakdown_ms": {"provider": 1},
        }


def test_single_day_daily_fetch_refreshes_exact_miniqmt_cache_first() -> None:
    bridge = RecordingBridge()
    request = CanonicalDatasetRequest(
        dataset_name="broad_index_daily",
        as_of=datetime.now(UTC),
        start_date=date(2026, 7, 30),
        end_date=date(2026, 7, 30),
        universe=("000001.SH",),
        fields=("instrument_id", "trade_date", "open", "high", "low", "close"),
    )

    batch = asyncio.run(
        MiniQMTSourceAdapter(bridge).fetch(request)  # type: ignore[arg-type]
    )

    assert [command for command, _ in bridge.calls] == [
        "fetch",
        "prepare_history_cache",
        "fetch",
    ]
    preparation = bridge.calls[1][1]
    assert preparation["start_time"] == "20260730"
    assert preparation["end_time"] == "20260730"
    assert preparation["universe"] == ("000001.SH",)
    assert preparation["timeout_seconds"] == 120
    fetch_request = bridge.calls[0][1]["request"]
    assert isinstance(fetch_request, dict)
    assert fetch_request["filters"]["start_time"] == ""
    assert fetch_request["filters"]["end_time"] == "20260730"
    assert batch.native_interface == "download_history_data2+get_market_data"
    assert len(batch.rows) == 1


def test_multi_day_fetch_does_not_mutate_provider_cache() -> None:
    bridge = RecordingBridge()
    request = CanonicalDatasetRequest(
        dataset_name="daily_market",
        as_of=datetime.now(UTC),
        start_date=date(2026, 7, 29),
        end_date=date(2026, 7, 30),
        universe=("000001.SH",),
        fields=("instrument_id", "trade_date", "close"),
    )

    asyncio.run(MiniQMTSourceAdapter(bridge).fetch(request))  # type: ignore[arg-type]

    assert [command for command, _ in bridge.calls] == ["fetch"]
