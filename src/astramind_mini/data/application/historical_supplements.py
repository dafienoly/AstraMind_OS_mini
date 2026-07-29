"""Fetch only market sessions missing from the legacy Silver release."""

from __future__ import annotations

from datetime import date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

import duckdb

from ..ports import HistoricalMarketDataProvider, ParquetEncoder, ProviderTable, RawRecordStore
from .dataset_schemas import ADJUSTMENT_FACTOR_COLUMNS, DAILY_BAR_COLUMNS
from .normalization import normalize_adjustment_factors, normalize_daily_bars
from .provider_lineage import market_artifact_matches_epoch
from .publication_policy import ADJUSTMENT_FIELDS, DAILY_FIELDS, PROVIDER_LIMIT
from .raw_records import preserve_provider_table_raw
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
        daily_universe: dict[date, tuple[str, ...]] | None = None,
    ) -> None:
        supplements = state["supplements"]
        assert isinstance(supplements, dict)
        for trade_date in sorted(missing_daily | missing_factors):
            key = trade_date.isoformat()
            entry = supplements.setdefault(key, {})
            assert isinstance(entry, dict)
            daily_path = Path(str(entry.get("daily", "")))
            if (
                trade_date in missing_daily
                and "daily" in entry
                and (
                    not daily_path.is_file()
                    or not market_artifact_matches_epoch(daily_path, trade_date)
                )
            ):
                for field in ("daily", "daily_request_identity", "daily_received_at"):
                    entry.pop(field, None)
                save_state(state_path, state)
            if trade_date in missing_daily and "daily" not in entry:
                table = await self._fetch(
                    "daily",
                    trade_date,
                    DAILY_FIELDS,
                    universe=(daily_universe or {}).get(trade_date, ()),
                )
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
        *,
        universe: tuple[str, ...] = (),
    ) -> ProviderTable:
        params: dict[str, object] = {"trade_date": trade_date.strftime("%Y%m%d")}
        if universe:
            params["universe"] = universe
        table = await self._provider.query(
            api_name,
            params=params,
            fields=fields,
        )
        if not table.rows:
            raise ValueError(f"{api_name} {trade_date} 返回空数据")
        if len(table.rows) >= PROVIDER_LIMIT:
            raise ValueError(f"{api_name} 达到提供方行数上限")
        preserve_provider_table_raw(table, self._raw_store)
        return table


def historical_availability(value: date) -> datetime:
    return datetime.combine(value, time(18), tzinfo=SHANGHAI)


def validate_daily_market_coverage(
    daily_path: Path,
    daily_basic_path: Path,
    target_date: date,
) -> tuple[int, int]:
    """Require every security with same-day fundamentals to have a market bar."""
    with duckdb.connect(":memory:") as connection:
        result = connection.execute(
            """
            SELECT
              (SELECT count(DISTINCT instrument_id)
               FROM read_parquet(?) WHERE trade_date = ?),
              (SELECT count(DISTINCT instrument_id)
               FROM read_parquet(?) WHERE trade_date = ?),
              (SELECT count(*) FROM (
                 SELECT instrument_id
                 FROM read_parquet(?) WHERE trade_date = ?
                 EXCEPT
                 SELECT instrument_id
                 FROM read_parquet(?) WHERE trade_date = ?
              ))
            """,
            [
                str(daily_path),
                target_date,
                str(daily_basic_path),
                target_date,
                str(daily_basic_path),
                target_date,
                str(daily_path),
                target_date,
            ],
        ).fetchone()
    assert result is not None
    observed, expected, missing = result
    if missing:
        raise ValueError(
            "日线行情覆盖不完整："
            f"target_date={target_date},observed={observed},expected={expected},missing={missing}"
        )
    return int(observed), int(expected)


__all__ = [
    "HistoricalSupplementService",
    "historical_availability",
    "validate_daily_market_coverage",
]
