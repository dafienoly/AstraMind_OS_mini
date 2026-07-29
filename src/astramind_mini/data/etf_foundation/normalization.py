"""Normalize provider ETF facts without changing the upstream records."""

from __future__ import annotations

from dataclasses import asdict
from datetime import date, datetime, time
from typing import Any, Literal, TypedDict
from zoneinfo import ZoneInfo

from astramind_mini.data.application.identity import content_hash
from astramind_mini.data.ports import ProviderTable

from .contracts import (
    EtfDailyObservation,
    EtfIndustryMappingObservation,
    EtfMasterObservation,
    EtfShareObservation,
)
from .registry import (
    ETF_CODES,
    ETF_MAPPINGS,
    MAPPING_EFFECTIVE_FROM,
    MAPPING_VERSION,
)

SHANGHAI = ZoneInfo("Asia/Shanghai")
SCHEMA_VERSION = "1.0.0"


class SourceFields(TypedDict):
    provider: str
    source_endpoint: str
    retrieved_at: datetime
    available_at: datetime
    schema_version: str
    source_record_hash: str


def normalize_master(table: ProviderTable) -> tuple[EtfMasterObservation, ...]:
    rows = []
    for raw in table.rows:
        code = str(raw.get("ts_code", ""))
        if code not in ETF_CODES:
            continue
        list_date = _date(raw.get("list_date"))
        if list_date is None:
            raise ValueError(f"ETF 主表缺少上市日：{code}")
        status_value = str(raw.get("status") or "L")
        if status_value not in {"L", "D"}:
            raise ValueError(f"ETF 主表状态无效：{code}:{status_value}")
        status: Literal["L", "D"] = "L" if status_value == "L" else "D"
        rows.append(
            EtfMasterObservation(
                **_source(table, raw, table.received_at),
                instrument_id=code,
                name=str(raw.get("name") or code),
                fund_type=_text(raw.get("fund_type")),
                invest_type=_text(raw.get("invest_type")),
                benchmark=_text(raw.get("benchmark")),
                exchange=_exchange(code),
                found_date=_date(raw.get("found_date")),
                list_date=list_date,
                delist_date=_date(raw.get("delist_date")),
                list_status=status,
            )
        )
    unique = {row.instrument_id: row for row in rows}
    if len(unique) != len(rows):
        raise ValueError("ETF 主表包含重复代码")
    missing = set(ETF_CODES) - unique.keys()
    if missing:
        raise ValueError("ETF 白名单未被主表确认：" + ",".join(sorted(missing)))
    return tuple(unique[code] for code in sorted(unique))


def normalize_daily(table: ProviderTable) -> tuple[EtfDailyObservation, ...]:
    rows = []
    for raw in table.rows:
        code = str(raw.get("ts_code", ""))
        if code not in ETF_CODES:
            raise ValueError(f"ETF 日线返回白名单外代码：{code}")
        trade_date = _required_date(raw.get("trade_date"), f"ETF 日线缺少日期：{code}")
        open_ = _positive_float(raw.get("open"), f"ETF 日线开盘无效：{code}:{trade_date}")
        high = _positive_float(raw.get("high"), f"ETF 日线最高无效：{code}:{trade_date}")
        low = _positive_float(raw.get("low"), f"ETF 日线最低无效：{code}:{trade_date}")
        close = _positive_float(raw.get("close"), f"ETF 日线收盘无效：{code}:{trade_date}")
        previous = _positive_float(
            raw.get("pre_close"),
            f"ETF 日线昨收无效：{code}:{trade_date}",
        )
        volume = _float(raw.get("vol")) or 0.0
        amount = _float(raw.get("amount")) or 0.0
        rows.append(
            EtfDailyObservation(
                **_source(table, raw, _available(trade_date)),
                instrument_id=code,
                trade_date=trade_date,
                open=open_,
                high=high,
                low=low,
                close=close,
                previous_close=previous,
                change=_float(raw.get("change")) or close - previous,
                percent_change=_float(raw.get("pct_chg")) or 100.0 * (close / previous - 1.0),
                volume_lots=volume,
                amount_cny=amount * 1000.0,
            )
        )
    return _unique(rows, lambda row: (row.instrument_id, row.trade_date), "ETF 日线")


def normalize_share(table: ProviderTable) -> tuple[EtfShareObservation, ...]:
    rows = []
    for raw in table.rows:
        code = str(raw.get("ts_code", ""))
        if code not in ETF_CODES:
            raise ValueError(f"ETF 份额返回白名单外代码：{code}")
        trade_date = _required_date(raw.get("trade_date"), f"ETF 份额缺少日期：{code}")
        share = _float(raw.get("fd_share"))
        if share is None or share <= 0:
            raise ValueError(f"ETF 份额无效：{code}:{trade_date}")
        rows.append(
            EtfShareObservation(
                **_source(table, raw, table.received_at),
                instrument_id=code,
                trade_date=trade_date,
                fund_share=share * 10_000.0,
            )
        )
    return _unique(rows, lambda row: (row.instrument_id, row.trade_date), "ETF 份额")


def mapping_observations(retrieved_at: datetime) -> tuple[EtfIndustryMappingObservation, ...]:
    available_at = _available(MAPPING_EFFECTIVE_FROM)
    return tuple(
        EtfIndustryMappingObservation(
            provider="astramind-registry",
            source_endpoint=MAPPING_VERSION,
            retrieved_at=retrieved_at,
            available_at=available_at,
            schema_version=SCHEMA_VERSION,
            source_record_hash=content_hash(asdict(row)),
            taxonomy="SW",
            taxonomy_version="SW2021",
            industry_code=row.industry_code,
            industry_name=row.industry_name,
            etf_code=row.etf_code,
            semantic_tier=row.tier,
            tracked_index=row.tracked_index,
            eligible_for_foundation=row.eligible,
            effective_from=MAPPING_EFFECTIVE_FROM,
            mapping_version=MAPPING_VERSION,
            evidence_source="accepted-methodology-adapted-to-sw2021-l1",
        )
        for row in ETF_MAPPINGS
    )


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


def _unique[Row: (EtfDailyObservation, EtfShareObservation)](
    rows: list[Row],
    key: Any,
    label: str,
) -> tuple[Row, ...]:
    unique = {key(row): row for row in rows}
    if len(unique) != len(rows):
        raise ValueError(f"{label}包含重复主键")
    return tuple(unique[item] for item in sorted(unique))


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


def _float(value: object) -> float | None:
    if value is None or str(value).strip() == "":
        return None
    return float(str(value))


def _positive_float(value: object, message: str) -> float:
    number = _float(value)
    if number is None or number <= 0:
        raise ValueError(message)
    return number


def _text(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None


def _exchange(code: str) -> Literal["SSE", "SZSE"]:
    if code.endswith(".SH"):
        return "SSE"
    if code.endswith(".SZ"):
        return "SZSE"
    raise ValueError(f"ETF 交易所后缀无效：{code}")


__all__ = [
    "mapping_observations",
    "normalize_daily",
    "normalize_master",
    "normalize_share",
]
