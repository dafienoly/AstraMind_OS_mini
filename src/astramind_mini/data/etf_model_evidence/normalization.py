"""Normalize official ETF evidence without inventing historical availability."""

from __future__ import annotations

from datetime import date, datetime, time
from typing import Any, TypedDict
from zoneinfo import ZoneInfo

from astramind_mini.data.application.identity import content_hash
from astramind_mini.data.etf_foundation.registry import ETF_CODES
from astramind_mini.data.ports import ProviderTable

from .contracts import (
    EtfNavObservation,
    EtfOfficialBenchmarkObservation,
    OfficialIndexDailyObservation,
)

SHANGHAI = ZoneInfo("Asia/Shanghai")
SCHEMA_VERSION = "1.0.0"
MARKET_MODEL_BENCHMARK = "000985.CSI"


class SourceFields(TypedDict):
    provider: str
    source_endpoint: str
    retrieved_at: datetime
    available_at: datetime
    schema_version: str
    source_record_hash: str


def normalize_official_benchmarks(
    table: ProviderTable,
) -> tuple[EtfOfficialBenchmarkObservation, ...]:
    observed: dict[str, EtfOfficialBenchmarkObservation] = {}
    effective = table.received_at.astimezone(SHANGHAI).date()
    for raw in table.rows:
        code = str(raw.get("ts_code") or "")
        if code not in ETF_CODES:
            continue
        index_code = _text(raw.get("index_code"))
        index_name = _text(raw.get("index_name"))
        if index_code is None or index_name is None:
            raise ValueError(f"ETF 官方基准缺失：{code}")
        if code in observed:
            raise ValueError(f"ETF 官方基准重复：{code}")
        observed[code] = EtfOfficialBenchmarkObservation(
            **_source(table, raw, table.received_at),
            instrument_id=code,
            benchmark_code=index_code,
            benchmark_name=index_name,
            effective_from=effective,
            historical_availability_known=False,
            evidence_kind="provider_current_registry",
        )
    if missing := set(ETF_CODES) - observed.keys():
        raise ValueError("ETF 官方基准未覆盖白名单：" + ",".join(sorted(missing)))
    return tuple(observed[code] for code in sorted(observed))


def normalize_nav(table: ProviderTable) -> tuple[EtfNavObservation, ...]:
    rows: dict[tuple[str, date], EtfNavObservation] = {}
    for raw in table.rows:
        code = str(raw.get("ts_code") or "")
        if code not in ETF_CODES:
            raise ValueError(f"ETF NAV 返回白名单外代码：{code}")
        nav_date = _required_date(raw.get("nav_date"), f"ETF NAV 缺少净值日：{code}")
        announced = _required_date(
            raw.get("ann_date"),
            f"ETF NAV 缺少公告日：{code}:{nav_date}",
        )
        if announced < nav_date:
            raise ValueError(f"ETF NAV 公告日早于净值日：{code}:{nav_date}")
        unit_nav = _positive(raw.get("unit_nav"), f"ETF NAV 单位净值无效：{code}:{nav_date}")
        observation = EtfNavObservation(
            **_source(table, raw, _available(announced)),
            instrument_id=code,
            nav_date=nav_date,
            announced_on=announced,
            unit_nav=unit_nav,
            accumulated_nav=_optional_positive(raw.get("accum_nav")),
            adjusted_nav=_optional_positive(raw.get("adj_nav")),
        )
        key = code, nav_date
        if key in rows:
            raise ValueError(f"ETF NAV 主键重复：{code}:{nav_date}")
        rows[key] = observation
    return tuple(rows[key] for key in sorted(rows))


def normalize_official_index_daily(
    table: ProviderTable,
    *,
    allowed_codes: frozenset[str],
) -> tuple[OfficialIndexDailyObservation, ...]:
    rows: dict[tuple[str, date], OfficialIndexDailyObservation] = {}
    for raw in table.rows:
        code = str(raw.get("ts_code") or "")
        if code not in allowed_codes:
            raise ValueError(f"官方指数日线返回未请求代码：{code}")
        trade_date = _required_date(
            raw.get("trade_date"),
            f"官方指数日线缺少交易日：{code}",
        )
        close = _positive(raw.get("close"), f"官方指数收盘无效：{code}:{trade_date}")
        previous = _optional_positive(raw.get("pre_close"))
        change = _number(raw.get("change"))
        percent_change = _number(raw.get("pct_chg"))
        observation = OfficialIndexDailyObservation(
            **_source(table, raw, _available(trade_date)),
            index_code=code,
            trade_date=trade_date,
            open=_optional_positive(raw.get("open")),
            high=_optional_positive(raw.get("high")),
            low=_optional_positive(raw.get("low")),
            close=close,
            previous_close=previous,
            change=change
            if change is not None
            else (close - previous if previous is not None else None),
            percent_change=percent_change
            if percent_change is not None
            else (100.0 * (close / previous - 1.0) if previous is not None else None),
            volume=_nonnegative(raw.get("vol")),
            amount=_nonnegative(raw.get("amount")),
        )
        key = code, trade_date
        if key in rows:
            raise ValueError(f"官方指数日线主键重复：{code}:{trade_date}")
        rows[key] = observation
    return tuple(rows[key] for key in sorted(rows))


def _source(
    table: ProviderTable,
    raw: dict[str, Any],
    available_at: datetime,
) -> SourceFields:
    return {
        "provider": table.provider_id,
        "source_endpoint": table.source_endpoint,
        "retrieved_at": table.received_at,
        "available_at": available_at,
        "schema_version": SCHEMA_VERSION,
        "source_record_hash": content_hash(raw),
    }


def _available(day: date) -> datetime:
    return datetime.combine(day, time(18), tzinfo=SHANGHAI)


def _required_date(value: object, message: str) -> date:
    parsed = _date(value)
    if parsed is None:
        raise ValueError(message)
    return parsed


def _date(value: object) -> date | None:
    text = str(value or "").strip().replace("-", "")
    if not text:
        return None
    return datetime.strptime(text, "%Y%m%d").date()


def _text(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None


def _number(value: object) -> float | None:
    if value in {None, ""}:
        return None
    return float(str(value))


def _positive(value: object, message: str) -> float:
    parsed = _number(value)
    if parsed is None or parsed <= 0:
        raise ValueError(message)
    return parsed


def _optional_positive(value: object) -> float | None:
    parsed = _number(value)
    return parsed if parsed is not None and parsed > 0 else None


def _nonnegative(value: object) -> float | None:
    parsed = _number(value)
    return parsed if parsed is not None and parsed >= 0 else None


__all__ = [
    "MARKET_MODEL_BENCHMARK",
    "normalize_nav",
    "normalize_official_benchmarks",
    "normalize_official_index_daily",
]
