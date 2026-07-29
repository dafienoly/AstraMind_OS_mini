"""Fetch only market sessions missing from the legacy Silver release."""

from __future__ import annotations

from datetime import date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

from ..contracts import RawRecordEnvelope
from ..ports import HistoricalMarketDataProvider, ParquetEncoder, ProviderTable, RawRecordStore
from .dataset_schemas import ADJUSTMENT_FACTOR_COLUMNS, DAILY_BAR_COLUMNS
from .identity import content_hash
from .normalization import normalize_adjustment_factors, normalize_daily_bars
from .publication_policy import ADJUSTMENT_FIELDS, DAILY_FIELDS, PROVIDER_LIMIT
from .state_files import save_state, write_bytes_atomic

SHANGHAI = ZoneInfo("Asia/Shanghai")


class HistoricalSupplementService:
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
        missing_daily: frozenset[date],
        missing_factors: frozenset[date],
    ) -> None:
        supplements = state["supplements"]
        assert isinstance(supplements, dict)
        for trade_date in sorted(missing_daily | missing_factors):
            key = trade_date.isoformat()
            entry = supplements.setdefault(key, {})
            assert isinstance(entry, dict)
            if trade_date in missing_daily and "daily" not in entry:
                table = await self._fetch("daily", trade_date, DAILY_FIELDS)
                daily_observations = tuple(
                    row.model_copy(
                        update={
                            "available_at": historical_availability(trade_date),
                            "schema_version": "1.1.0",
                        }
                    )
                    for row in normalize_daily_bars(table)
                )
                path = staging / "supplements" / "daily" / f"{key}.parquet"
                write_bytes_atomic(
                    path,
                    self._encoder.encode(daily_observations, DAILY_BAR_COLUMNS),
                )
                entry["daily"] = str(path)
                entry["daily_request_identity"] = table.request_identity
                entry["daily_received_at"] = table.received_at.isoformat()
                save_state(state_path, state)
            if trade_date in missing_factors and "adj_factor" not in entry:
                table = await self._fetch("adj_factor", trade_date, ADJUSTMENT_FIELDS)
                factor_observations = tuple(
                    row.model_copy(
                        update={
                            "available_at": historical_availability(trade_date),
                            "schema_version": "1.1.0",
                        }
                    )
                    for row in normalize_adjustment_factors(table)
                )
                path = staging / "supplements" / "adj_factor" / f"{key}.parquet"
                write_bytes_atomic(
                    path,
                    self._encoder.encode(factor_observations, ADJUSTMENT_FACTOR_COLUMNS),
                )
                entry["adj_factor"] = str(path)
                entry["factor_request_identity"] = table.request_identity
                entry["factor_received_at"] = table.received_at.isoformat()
                save_state(state_path, state)

    async def _fetch(
        self,
        api_name: str,
        trade_date: date,
        fields: tuple[str, ...],
    ) -> ProviderTable:
        table = await self._provider.query(
            api_name,
            params={"trade_date": trade_date.strftime("%Y%m%d")},
            fields=fields,
        )
        if not table.rows:
            raise ValueError(f"{api_name} {trade_date} 返回空数据")
        if len(table.rows) >= PROVIDER_LIMIT:
            raise ValueError(f"{api_name} 达到提供方行数上限")
        envelope = RawRecordEnvelope(
            provider="tushare",
            interface_name=api_name,
            source_endpoint=table.source_endpoint,
            request_identity=table.request_identity,
            received_at=table.received_at,
            schema_version="provider-v1",
            content_hash=content_hash(table.raw_body),
        )
        self._raw_store.append(envelope, table.raw_body)
        return table


def historical_availability(value: date) -> datetime:
    return datetime.combine(value, time(18), tzinfo=SHANGHAI)


__all__ = ["HistoricalSupplementService", "historical_availability"]
