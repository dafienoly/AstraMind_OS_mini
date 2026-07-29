"""Provider collection helpers for the WP-0025 daily pipeline."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Literal, cast

import duckdb

from ..adapters import FilesystemRawRecordStore
from ..ports import HistoricalMarketDataProvider, ParquetEncoder, ProviderTable
from .broad_index_normalization import (
    BROAD_INDEX_REGISTRY,
    normalize_broad_index_daily,
)
from .broad_index_normalization import (
    INDEX_DAILY_FIELDS as BROAD_INDEX_DAILY_FIELDS,
)
from .dataset_schemas import (
    BROAD_INDEX_DAILY_COLUMNS,
    INDUSTRY_INDEX_DAILY_COLUMNS,
    TRADE_CALENDAR_COLUMNS,
)
from .identity import file_hash
from .industry_foundation_support import INDEX_DAILY_FIELDS
from .industry_normalization import normalize_index_daily
from .normalization import normalize_trade_calendar
from .provider_lineage import market_artifact_matches_epoch
from .raw_records import preserve_provider_table_raw
from .state_files import save_state, write_bytes_atomic


async def collect_calendar(
    *,
    state: dict[str, object],
    state_path: Path,
    workspace: Path,
    target_date: date,
    provider: HistoricalMarketDataProvider,
    encoder: ParquetEncoder,
    raw_store: FilesystemRawRecordStore,
) -> tuple[bool, Path, datetime]:
    cached = state.get("calendar")
    if isinstance(cached, dict):
        path = Path(str(cached["path"]))
        if path.is_file() and file_hash(path) == cached["hash"]:
            return (
                bool(cached["is_open"]),
                path,
                datetime.fromisoformat(str(cached["received_at"])),
            )
    table = await provider.query(
        "trade_cal",
        params={
            "exchange": "SSE",
            "start_date": f"{target_date:%Y%m%d}",
            "end_date": f"{target_date + timedelta(days=14):%Y%m%d}",
        },
        fields=("exchange", "cal_date", "is_open", "pretrade_date"),
    )
    preserve_raw(table, raw_store)
    matching = [row for row in table.rows if str(row.get("cal_date")) == f"{target_date:%Y%m%d}"]
    if len(matching) != 1:
        raise ValueError("提供方交易日历没有唯一目标日期")
    rows = normalize_trade_calendar((table,))
    path = workspace / "requests" / "trade_calendar.parquet"
    write_bytes_atomic(path, encoder.encode(rows, TRADE_CALENDAR_COLUMNS))
    state["calendar"] = {
        "is_open": str(matching[0].get("is_open")) == "1",
        "path": str(path),
        "hash": file_hash(path),
        "received_at": table.received_at.isoformat(),
        "request_identity": table.request_identity,
    }
    save_state(state_path, state)
    return (
        bool(as_dict(state["calendar"])["is_open"]),
        path,
        table.received_at,
    )


async def collect_industries(
    *,
    state: dict[str, object],
    state_path: Path,
    workspace: Path,
    industries: tuple[tuple[str, str, str], ...],
    target_date: date,
    provider: HistoricalMarketDataProvider,
    encoder: ParquetEncoder,
    raw_store: FilesystemRawRecordStore,
) -> tuple[tuple[Path, ...], datetime, int, int]:
    entries = as_dict(state["industries"])
    for level, code, name in industries:
        cached = entries.get(code)
        if isinstance(cached, dict):
            path = Path(str(cached["path"]))
            if path.is_file() and file_hash(path) == cached["hash"]:
                continue
        table = await provider.query(
            "sw_daily",
            params={
                "ts_code": code,
                "start_date": f"{target_date:%Y%m%d}",
                "end_date": f"{target_date:%Y%m%d}",
            },
            fields=INDEX_DAILY_FIELDS,
        )
        preserve_raw(table, raw_store)
        rows = normalize_index_daily(
            table,
            industry_name=name,
            level=cast(Literal["L1", "L2"], level),
        )
        if any(row.trade_date != target_date or row.industry_code != code for row in rows):
            raise ValueError("提供方返回了请求范围外的行业日线")
        if len(rows) > 1:
            raise ValueError("提供方返回重复行业日线")
        if not rows:
            continue
        path = workspace / "requests" / level / f"{code}.parquet"
        write_bytes_atomic(
            path,
            encoder.encode(rows, INDUSTRY_INDEX_DAILY_COLUMNS),
        )
        entries[code] = {
            "level": level,
            "path": str(path),
            "hash": file_hash(path),
            "received_at": table.received_at.isoformat(),
            "request_identity": table.request_identity,
        }
        save_state(state_path, state)
    valid = [
        value
        for value in entries.values()
        if isinstance(value, dict)
        and Path(str(value.get("path", ""))).is_file()
        and file_hash(Path(str(value["path"]))) == value.get("hash")
    ]
    received = [datetime.fromisoformat(str(value["received_at"])) for value in valid]
    calendar = as_dict(state["calendar"])
    received.append(datetime.fromisoformat(str(calendar["received_at"])))
    return (
        tuple(sorted(Path(str(value["path"])) for value in valid)),
        max(received),
        sum(value["level"] == "L1" for value in valid),
        sum(value["level"] == "L2" for value in valid),
    )


async def collect_broad_indexes(
    *,
    state: dict[str, object],
    state_path: Path,
    workspace: Path,
    target_date: date,
    provider: HistoricalMarketDataProvider,
    encoder: ParquetEncoder,
    raw_store: FilesystemRawRecordStore,
) -> tuple[Path, datetime, int]:
    entries = state.setdefault("broad_indexes", {})
    if not isinstance(entries, dict):
        raise ValueError("日度宽基指数状态格式无效")
    for code in BROAD_INDEX_REGISTRY:
        cached = entries.get(code)
        if isinstance(cached, dict):
            path = Path(str(cached["path"]))
            if (
                path.is_file()
                and file_hash(path) == cached["hash"]
                and market_artifact_matches_epoch(path, target_date)
            ):
                continue
            entries.pop(code)
            save_state(state_path, state)
        table = await provider.query(
            "index_daily",
            params={
                "ts_code": code,
                "start_date": f"{target_date:%Y%m%d}",
                "end_date": f"{target_date:%Y%m%d}",
            },
            fields=BROAD_INDEX_DAILY_FIELDS,
        )
        preserve_raw(table, raw_store)
        rows = normalize_broad_index_daily(table)
        if any(row.trade_date != target_date or row.instrument_id != code for row in rows):
            raise ValueError("提供方返回了请求范围外的宽基指数日线")
        if len(rows) > 1:
            raise ValueError("提供方返回重复宽基指数日线")
        if not rows:
            continue
        path = workspace / "requests" / "broad_index" / f"{code}.parquet"
        write_bytes_atomic(path, encoder.encode(rows, BROAD_INDEX_DAILY_COLUMNS))
        entries[code] = {
            "path": str(path),
            "hash": file_hash(path),
            "received_at": table.received_at.isoformat(),
            "request_identity": table.request_identity,
        }
        save_state(state_path, state)
    valid = [
        value
        for value in entries.values()
        if isinstance(value, dict)
        and Path(str(value.get("path", ""))).is_file()
        and file_hash(Path(str(value["path"]))) == value.get("hash")
    ]
    received = [datetime.fromisoformat(str(value["received_at"])) for value in valid]
    calendar = as_dict(state["calendar"])
    received.append(datetime.fromisoformat(str(calendar["received_at"])))
    output = workspace / "requests" / "broad_index_daily.parquet"
    if valid:
        sources = [str(value["path"]) for value in valid]
        output.parent.mkdir(parents=True, exist_ok=True)
        target = str(output).replace("'", "''")
        with duckdb.connect(":memory:") as connection:
            connection.execute(
                "COPY (SELECT * FROM read_parquet(?) ORDER BY instrument_id) "
                f"TO '{target}' (FORMAT PARQUET, COMPRESSION ZSTD)",
                [sources],
            )
    return output, max(received), len(valid)


def preserve_raw(table: ProviderTable, raw_store: FilesystemRawRecordStore) -> None:
    preserve_provider_table_raw(table, raw_store)


def as_dict(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError("日度运行状态格式无效")
    return value


__all__ = ["collect_broad_indexes", "collect_calendar", "collect_industries"]
