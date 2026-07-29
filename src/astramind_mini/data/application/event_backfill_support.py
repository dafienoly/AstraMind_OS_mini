"""Constants and resumable-state helpers for tactical event backfill."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

from astramind_mini.contracts import DataSnapshot

from ..contracts import DatasetManifest
from .identity import file_hash

LHB_FIELDS = (
    "trade_date",
    "ts_code",
    "name",
    "close",
    "pct_change",
    "turnover_rate",
    "amount",
    "l_sell",
    "l_buy",
    "l_amount",
    "net_amount",
    "net_rate",
    "amount_rate",
    "float_values",
    "reason",
)
SEAT_FIELDS = (
    "trade_date",
    "ts_code",
    "exalter",
    "side",
    "buy",
    "buy_rate",
    "sell",
    "sell_rate",
    "net_buy",
    "reason",
)
HOLDER_FIELDS = ("ts_code", "ann_date", "end_date", "holder_num")


@dataclass(frozen=True, slots=True)
class EventBackfillPublication:
    snapshot: DataSnapshot
    manifests: tuple[DatasetManifest, ...]
    request_count: int


def artifact_paths(data_root: Path, manifest: DatasetManifest) -> tuple[Path, ...]:
    digest = manifest.dataset_version.rsplit(":", 1)[-1]
    base = data_root / "datasets" / manifest.dataset_name / digest
    paths = tuple(base / name for name in manifest.artifact_paths if name.endswith(".parquet"))
    if not paths or any(not path.is_file() for path in paths):
        raise ValueError(f"{manifest.dataset_name} 精确 Parquet 不完整")
    return paths


def seven_day_windows(start: date, end: date) -> tuple[tuple[date, date], ...]:
    result = []
    current = start
    while current <= end:
        window_end = min(end, current + timedelta(days=6))
        result.append((current, window_end))
        current = window_end + timedelta(days=1)
    return tuple(result)


def year_bounded_seven_day_windows(start: date, end: date) -> tuple[tuple[date, date], ...]:
    return tuple(
        window
        for year in range(start.year, end.year + 1)
        for window in seven_day_windows(
            max(start, date(year, 1, 1)),
            min(end, date(year, 12, 31)),
        )
    )


def request_is_intact(value: dict[str, object]) -> bool:
    path = Path(str(value.get("path", "")))
    return path.is_file() and file_hash(path) == value.get("hash")


def request_paths(
    requests: dict[object, object],
    api_name: str,
    year: int,
) -> tuple[Path, ...]:
    result = []
    for value in requests.values():
        if not isinstance(value, dict) or value.get("api_name") != api_name:
            continue
        key = str(value.get("key", ""))
        if api_name == "stk_holdernumber" and "-" not in key:
            continue
        if api_name == "stk_holdernumber" and key[9:13] != str(year):
            continue
        if key[:4] == str(year) and request_is_intact(value):
            result.append(Path(str(value["path"])))
    if not result:
        raise ValueError(f"{api_name}:{year} 没有完整请求分区")
    return tuple(sorted(result))


def latest_received_at(state: dict[str, object]) -> datetime:
    requests = state["requests"]
    assert isinstance(requests, dict)
    values = [
        datetime.fromisoformat(str(value["received_at"]))
        for value in requests.values()
        if isinstance(value, dict)
    ]
    if not values:
        raise ValueError("事件回填没有成功请求")
    return max(values)


def request_count(state: dict[str, object]) -> int:
    requests = state["requests"]
    if not isinstance(requests, dict):
        raise ValueError("事件回填请求状态无效")
    return len(requests)


__all__ = [
    "HOLDER_FIELDS",
    "LHB_FIELDS",
    "SEAT_FIELDS",
    "EventBackfillPublication",
    "artifact_paths",
    "latest_received_at",
    "request_count",
    "request_is_intact",
    "request_paths",
    "seven_day_windows",
    "year_bounded_seven_day_windows",
]
