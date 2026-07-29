"""Fetch only legacy gaps needed by the WP-0002B-H2 datasets."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

from pydantic import BaseModel

from ..ports import HistoricalMarketDataProvider, ParquetEncoder, ProviderTable, RawRecordStore
from .dataset_schemas import DAILY_BASIC_COLUMNS, PRICE_LIMIT_COLUMNS, SUSPENSION_EVENT_COLUMNS
from .normalization import (
    normalize_daily_basic,
    normalize_price_limits,
    normalize_suspension_events,
)
from .publication_policy import DAILY_BASIC_FIELDS, PRICE_LIMIT_FIELDS, SUSPENSION_FIELDS
from .raw_records import preserve_provider_table_raw
from .state_files import save_state, write_bytes_atomic

SHANGHAI = ZoneInfo("Asia/Shanghai")
PROVIDER_LIMITS = {"daily_basic": 6000, "suspend_d": 6000}


class ConstraintSupplementService:
    def __init__(
        self,
        *,
        provider: HistoricalMarketDataProvider,
        raw_store: RawRecordStore,
        encoder: ParquetEncoder,
    ) -> None:
        self._provider = provider
        self._raw_store = raw_store
        self._encoder = encoder

    async def prepare(
        self,
        *,
        staging: Path,
        state: dict[str, object],
        state_path: Path,
        missing: dict[str, frozenset[date]],
    ) -> None:
        supplements = state["supplements"]
        assert isinstance(supplements, dict)
        for table in ("daily_basic", "stk_limit", "suspend_d"):
            table_state = supplements.setdefault(table, {})
            assert isinstance(table_state, dict)
            for trade_date in sorted(missing[table]):
                key = trade_date.isoformat()
                if key in table_state:
                    continue
                provider_table = await self._fetch(table, trade_date)
                rows, columns = _normalize(table, provider_table, trade_date)
                if table != "suspend_d" and not rows:
                    raise ValueError(f"{table} {trade_date} 返回空数据")
                path = staging / "supplements" / table / f"{key}.parquet"
                write_bytes_atomic(path, self._encoder.encode(rows, columns))
                table_state[key] = {
                    "path": str(path),
                    "request_identity": provider_table.request_identity,
                    "received_at": provider_table.received_at.isoformat(),
                    "rows": len(rows),
                }
                save_state(state_path, state)

    async def _fetch(self, api_name: str, trade_date: date) -> ProviderTable:
        if api_name == "stk_limit":
            table = await self._fetch_page(
                api_name,
                {"trade_date": trade_date.strftime("%Y%m%d")},
                fields=PRICE_LIMIT_FIELDS,
            )
            keys = {(row.get("ts_code"), row.get("trade_date")) for row in table.rows}
            if not table.rows or len(keys) != len(table.rows):
                raise ValueError("stk_limit 返回空数据或重复主键")
            return table
        fields = {
            "daily_basic": DAILY_BASIC_FIELDS,
            "suspend_d": SUSPENSION_FIELDS,
        }[api_name]
        table = await self._fetch_page(
            api_name,
            {"trade_date": trade_date.strftime("%Y%m%d")},
            fields=fields,
        )
        if len(table.rows) >= PROVIDER_LIMITS[api_name]:
            raise ValueError(f"{api_name} 达到提供方行数上限")
        return table

    async def _fetch_page(
        self,
        api_name: str,
        params: dict[str, object],
        *,
        fields: tuple[str, ...],
    ) -> ProviderTable:
        table = await self._provider.query(api_name, params=params, fields=fields)
        preserve_provider_table_raw(table, self._raw_store)
        return table


def _normalize(
    table: str,
    source: ProviderTable,
    trade_date: date,
) -> tuple[Sequence[BaseModel], tuple[tuple[str, str], ...]]:
    rows: Sequence[BaseModel]
    columns: tuple[tuple[str, str], ...]
    if table == "daily_basic":
        rows = normalize_daily_basic(source)
        columns = DAILY_BASIC_COLUMNS
    elif table == "stk_limit":
        rows = normalize_price_limits(source)
        columns = PRICE_LIMIT_COLUMNS
    else:
        rows = normalize_suspension_events(source)
        columns = SUSPENSION_EVENT_COLUMNS
    available_at = _availability(table, trade_date)
    normalized = tuple(
        row.model_copy(
            update={
                "available_at": available_at,
                "schema_version": "1.0.0",
            }
        )
        for row in rows
    )
    return normalized, columns


def _availability(table: str, value: date) -> datetime:
    provider_time = time(8, 40) if table == "stk_limit" else time(18)
    return datetime.combine(value, provider_time, tzinfo=SHANGHAI)


__all__ = ["ConstraintSupplementService"]
