from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime

from astramind_mini.data.adapters import TushareSourceAdapter
from astramind_mini.data.contracts import CanonicalDatasetRequest
from astramind_mini.data.ports import ProviderTable


class RecordingClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    async def query(
        self,
        api_name: str,
        *,
        params: dict[str, object],
        fields: tuple[str, ...],
    ) -> ProviderTable:
        self.calls.append((api_name, params))
        return ProviderTable(
            api_name=api_name,
            fields=fields,
            rows=(
                {"ts_code": "000001.SZ", "trade_date": "20260728", "close": 11.2},
                {"ts_code": "000002.SZ", "trade_date": "20260728", "close": 12.3},
                {"ts_code": "600000.SH", "trade_date": "20260728", "close": 10.1},
            ),
            raw_body={"source": "synthetic"},
            request_identity="sha256:" + "1" * 64,
            received_at=datetime.now(UTC),
            source_endpoint="test",
        )


def test_daily_cross_section_uses_one_provider_call_and_filters_universe() -> None:
    async def exercise() -> None:
        client = RecordingClient()
        adapter = TushareSourceAdapter(client)  # type: ignore[arg-type]
        request = CanonicalDatasetRequest(
            dataset_name="daily_market",
            as_of=datetime.now(UTC),
            start_date=date(2026, 7, 28),
            end_date=date(2026, 7, 28),
            universe=("000001.SZ", "000002.SZ"),
            fields=("instrument_id", "trade_date", "close"),
        )

        batch = await adapter.fetch(request)

        assert client.calls == [("daily", {"trade_date": "20260728"})]
        assert {row["instrument_id"] for row in batch.rows} == {
            "000001.SZ",
            "000002.SZ",
        }
        assert batch.completeness == 1
        assert batch.known_gaps == ()

    asyncio.run(exercise())
