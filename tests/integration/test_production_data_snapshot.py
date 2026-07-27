import asyncio
from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from astramind_mini.data.adapters import (
    DataControlLedger,
    DuckDBParquetEncoder,
    DuckDBSnapshotQuery,
    FilesystemDatasetStore,
    FilesystemRawRecordStore,
    FilesystemSnapshotStore,
)
from astramind_mini.data.application import ProductionSnapshotService, content_hash
from astramind_mini.data.ports import ProviderTable

RECEIVED_AT = datetime(2026, 1, 16, 10, 5, tzinfo=UTC)
TRADE_DATE = "20260115"


class SyntheticProvider:
    def __init__(
        self,
        *,
        truncated: bool = False,
        missing_factor: bool = False,
    ) -> None:
        self.truncated = truncated
        self.missing_factor = missing_factor

    async def query(
        self,
        api_name: str,
        *,
        params: Mapping[str, object],
        fields: Sequence[str],
    ) -> ProviderTable:
        rows = self._rows(api_name, params)
        body = {"code": 0, "data": {"fields": list(fields), "items": rows}}
        return ProviderTable(
            api_name=api_name,
            fields=tuple(fields),
            rows=rows,
            raw_body=body,
            request_identity=content_hash(
                {"api_name": api_name, "params": dict(params), "fields": list(fields)}
            ),
            received_at=RECEIVED_AT,
            source_endpoint="synthetic.tushare.local",
        )

    def _rows(
        self,
        api_name: str,
        params: Mapping[str, object],
    ) -> tuple[dict[str, object], ...]:
        if api_name == "stock_basic":
            if self.truncated:
                return tuple({"row": index} for index in range(6000))
            if params["list_status"] != "L":
                return ()
            return (
                {
                    "ts_code": "000001.SZ",
                    "symbol": "000001",
                    "name": "合成证券",
                    "area": "深圳",
                    "industry": "合成行业",
                    "market": "主板",
                    "exchange": "SZSE",
                    "curr_type": "CNY",
                    "list_status": "L",
                    "list_date": "19910403",
                    "delist_date": "",
                    "is_hs": "S",
                },
            )
        if api_name == "trade_cal":
            start = str(params["start_date"])
            end = str(params["end_date"])
            if start <= TRADE_DATE <= end:
                return (
                    {
                        "exchange": params["exchange"],
                        "cal_date": TRADE_DATE,
                        "is_open": "1",
                        "pretrade_date": "20260114",
                    },
                )
            return ()
        if api_name == "daily":
            return (
                {
                    "ts_code": "000001.SZ",
                    "trade_date": TRADE_DATE,
                    "open": 10.0,
                    "high": 10.5,
                    "low": 9.8,
                    "close": 10.2,
                    "pre_close": 10.0,
                    "change": 0.2,
                    "pct_chg": 2.0,
                    "vol": 100.0,
                    "amount": 1020.0,
                },
            )
        if api_name == "adj_factor":
            instrument_id = "000002.SZ" if self.missing_factor else "000001.SZ"
            return (
                {
                    "ts_code": instrument_id,
                    "trade_date": TRADE_DATE,
                    "adj_factor": 12.5,
                },
            )
        raise AssertionError(api_name)


def service(tmp_path: Path, provider: SyntheticProvider) -> ProductionSnapshotService:
    ledger = DataControlLedger(tmp_path / "control/data.db")
    ledger.migrate()
    return ProductionSnapshotService(
        provider=provider,
        raw_store=FilesystemRawRecordStore(tmp_path),
        dataset_store=FilesystemDatasetStore(tmp_path),
        snapshot_store=FilesystemSnapshotStore(tmp_path),
        ledger=ledger,
        encoder=DuckDBParquetEncoder(),
    )


def test_first_production_snapshot_is_versioned_queryable_and_repeatable(
    tmp_path: Path,
) -> None:
    publisher = service(tmp_path, SyntheticProvider())
    requested_at = datetime(2026, 1, 16, 9, 59, tzinfo=UTC)

    first = asyncio.run(publisher.publish(requested_at))
    second = asyncio.run(publisher.publish(requested_at))

    assert first.snapshot.snapshot_id == second.snapshot.snapshot_id
    assert first.latest_trade_date == date(2026, 1, 15)
    assert first.row_counts == {
        "security_master": 1,
        "trade_calendar": 2,
        "daily_market": 1,
        "adjustment_factor": 1,
    }
    assert len(first.snapshot.datasets) == 4
    assert "historical_daily_backfill_pending" in first.snapshot.known_gaps

    daily = next(item for item in first.manifests if item.dataset_name == "daily_market")
    rows = DuckDBSnapshotQuery(tmp_path).query_parquet(
        daily,
        "data.parquet",
        "SELECT instrument_id, trade_date, close, available_at FROM {dataset}",
    )
    assert rows[0][:3] == ("000001.SZ", date(2026, 1, 15), 10.2)
    assert rows[0][3] == RECEIVED_AT


def test_provider_limit_blocks_possible_truncation(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="行数上限"):
        asyncio.run(service(tmp_path, SyntheticProvider(truncated=True)).publish(RECEIVED_AT))


def test_daily_bar_without_adjustment_factor_blocks_publication(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="缺失复权因子"):
        asyncio.run(service(tmp_path, SyntheticProvider(missing_factor=True)).publish(RECEIVED_AT))
