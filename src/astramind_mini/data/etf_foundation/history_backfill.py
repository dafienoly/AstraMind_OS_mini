"""Offline planning and validation for ETF listed-since daily-history backfill."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Literal, cast

import duckdb

from astramind_mini.contracts import DatasetRef, DataSnapshot
from astramind_mini.contracts.base import ContentHash, ContractModel, Identifier
from astramind_mini.data.contracts import CanonicalDatasetRequest

from .service import DAILY_FIELDS


class EtfHistoryCoverage(ContractModel):
    instrument_id: Identifier
    listing_date: date
    observed_start: date | None = None
    observed_end: date | None = None
    state: Literal["complete", "backfill_required", "unavailable"]
    missing_start: date | None = None
    missing_end: date | None = None
    known_gaps: tuple[str, ...] = ()


class EtfHistoryBackfillPlan(ContractModel):
    base_snapshot_id: Identifier
    etf_master_version: ContentHash
    etf_daily_version: ContentHash
    evidence_cutoff: date
    coverage: tuple[EtfHistoryCoverage, ...]
    requests: tuple[CanonicalDatasetRequest, ...]
    state: Literal["complete", "backfill_required", "blocked"]
    raw_records_required: Literal[True] = True
    publish_new_dataset_version: Literal[True] = True
    rewrite_existing_version_allowed: Literal[False] = False
    activation_allowed: Literal[False] = False
    v2_training_allowed: Literal[False] = False
    historical_performance_allowed: Literal[False] = False
    known_gaps: tuple[str, ...] = ()


def plan_etf_history_backfill(
    data_root: Path,
    snapshot_id: str,
    *,
    evidence_cutoff: date | None = None,
) -> EtfHistoryBackfillPlan:
    snapshot = _snapshot(data_root, snapshot_id)
    references = {item.dataset_name: item for item in snapshot.datasets}
    if "etf_master" not in references or "etf_daily" not in references:
        raise ValueError("ETF 历史补采缺少 etf_master 或 etf_daily")
    cutoff = min(evidence_cutoff or snapshot.as_of.date(), snapshot.as_of.date())
    master_ref = references["etf_master"]
    daily_ref = references["etf_daily"]
    masters, observed = _coverage_inputs(data_root, master_ref, daily_ref, cutoff)
    coverage = []
    requests = []
    for instrument_id, listing_date in masters:
        start, end = observed.get(str(instrument_id), (None, None))
        item, request = _coverage_plan(
            snapshot,
            str(instrument_id),
            listing_date,
            observed_start=start,
            observed_end=end,
            cutoff=cutoff,
        )
        coverage.append(item)
        if request is not None:
            requests.append(request)
    if not coverage:
        state_value: Literal["complete", "backfill_required", "blocked"] = "blocked"
        plan_gaps: tuple[str, ...] = ("etf_master_has_no_available_instruments",)
    elif requests:
        state_value = "backfill_required"
        plan_gaps = ("provider_fetch_and_new_version_publication_pending",)
    else:
        state_value = "complete"
        plan_gaps = ()
    return EtfHistoryBackfillPlan(
        base_snapshot_id=snapshot.snapshot_id,
        etf_master_version=master_ref.dataset_version,
        etf_daily_version=daily_ref.dataset_version,
        evidence_cutoff=cutoff,
        coverage=tuple(coverage),
        requests=tuple(requests),
        state=state_value,
        known_gaps=plan_gaps,
    )


def _coverage_inputs(
    data_root: Path,
    master_ref: DatasetRef,
    daily_ref: DatasetRef,
    cutoff: date,
) -> tuple[list[tuple[str, date]], dict[str, tuple[date | None, date | None]]]:
    master_paths = _paths(data_root, "etf_master", master_ref.dataset_version)
    daily_paths = _paths(data_root, "etf_daily", daily_ref.dataset_version)
    with duckdb.connect(":memory:") as connection:
        masters = connection.execute(
            """
            SELECT instrument_id, list_date FROM read_parquet(?)
            WHERE list_date <= ? AND CAST(available_at AS DATE) <= ?
            ORDER BY instrument_id
            """,
            [master_paths, cutoff, cutoff],
        ).fetchall()
        observed_rows = connection.execute(
            """
            SELECT instrument_id, min(trade_date), max(trade_date)
            FROM read_parquet(?)
            WHERE trade_date <= ? AND CAST(available_at AS DATE) <= ?
            GROUP BY instrument_id
            """,
            [daily_paths, cutoff, cutoff],
        ).fetchall()
    master_values = [(str(row[0]), cast(date, row[1])) for row in masters]
    observed = {
        str(row[0]): (cast(date | None, row[1]), cast(date | None, row[2])) for row in observed_rows
    }
    return master_values, observed


def _coverage_plan(
    snapshot: DataSnapshot,
    instrument_id: str,
    listing_date: date,
    *,
    observed_start: date | None,
    observed_end: date | None,
    cutoff: date,
) -> tuple[EtfHistoryCoverage, CanonicalDatasetRequest | None]:
    if observed_start is not None and observed_start <= listing_date:
        return (
            EtfHistoryCoverage(
                instrument_id=instrument_id,
                listing_date=listing_date,
                observed_start=observed_start,
                observed_end=observed_end,
                state="complete",
            ),
            None,
        )
    missing_end = min(
        cutoff,
        date.fromordinal(observed_start.toordinal() - 1) if observed_start else cutoff,
    )
    state: Literal["backfill_required", "unavailable"] = (
        "backfill_required" if listing_date <= missing_end else "unavailable"
    )
    coverage = EtfHistoryCoverage(
        instrument_id=instrument_id,
        listing_date=listing_date,
        observed_start=observed_start,
        observed_end=observed_end,
        state=state,
        missing_start=listing_date,
        missing_end=missing_end,
        known_gaps=(f"etf_history_starts_after_listing:{listing_date.isoformat()}",),
    )
    if state != "backfill_required":
        return coverage, None
    return coverage, CanonicalDatasetRequest(
        dataset_name="etf_daily",
        as_of=snapshot.as_of,
        start_date=listing_date,
        end_date=missing_end,
        universe=(instrument_id,),
        fields=DAILY_FIELDS,
        frequency="1d",
        adjustment="none",
        point_in_time_policy="trade-date-18:00-asia-shanghai-v1",
    )


def validate_etf_history_backfill_rows(
    request: CanonicalDatasetRequest,
    rows: tuple[dict[str, object], ...],
) -> None:
    if len(request.universe) != 1 or request.start_date is None or request.end_date is None:
        raise ValueError("ETF 历史补采请求身份不完整")
    if request.dataset_name != "etf_daily" or request.fields != DAILY_FIELDS:
        raise ValueError("ETF 历史补采请求数据集或字段不匹配")
    if not rows:
        raise ValueError("ETF 历史补采响应为空，不能声明窗口已覆盖")
    instrument_id = request.universe[0]
    seen: set[tuple[str, date]] = set()
    for row in rows:
        code = str(row.get("ts_code", ""))
        trade_date = _trade_date(row.get("trade_date"))
        if code != instrument_id:
            raise ValueError("ETF 历史补采响应混入请求外证券")
        if not request.start_date <= trade_date <= request.end_date:
            raise ValueError("ETF 历史补采响应越过冻结日期窗口")
        key = (code, trade_date)
        if key in seen:
            raise ValueError("ETF 历史补采响应存在重复主键")
        seen.add(key)
        missing = [field for field in DAILY_FIELDS if field not in row]
        if missing:
            raise ValueError("ETF 历史补采响应缺字段：" + ",".join(missing))


def _trade_date(value: object) -> date:
    if isinstance(value, date):
        return value
    if not isinstance(value, str):
        raise ValueError("ETF 历史补采响应交易日无效")
    if len(value) == 8 and value.isdigit():
        return date(int(value[:4]), int(value[4:6]), int(value[6:]))
    return date.fromisoformat(value)


def _snapshot(data_root: Path, snapshot_id: str) -> DataSnapshot:
    digest = snapshot_id.removeprefix("snapshot:sha256:")
    snapshot = DataSnapshot.model_validate_json(
        (data_root / "snapshots" / digest / "manifest.json").read_text(encoding="utf-8")
    )
    if snapshot.snapshot_id != snapshot_id:
        raise ValueError("ETF 历史补采快照身份冲突")
    return snapshot


def _paths(data_root: Path, name: str, version: str) -> list[str]:
    directory = data_root / "datasets" / name / version.removeprefix("sha256:")
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("dataset_version") != version:
        raise ValueError(f"ETF 历史补采数据集身份冲突：{name}")
    return [
        str(directory / item)
        for item in manifest.get("artifact_paths", ())
        if str(item).endswith(".parquet")
    ]


__all__ = [
    "EtfHistoryBackfillPlan",
    "EtfHistoryCoverage",
    "plan_etf_history_backfill",
    "validate_etf_history_backfill_rows",
]
