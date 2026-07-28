"""Normalize SW2021 industry foundation records without inventing provider units."""

from __future__ import annotations

from datetime import date, datetime, time
from typing import TypedDict
from zoneinfo import ZoneInfo

from ..contracts import (
    IndustryIndexDailyObservation,
    IndustryMembershipObservation,
    IndustryTaxonomyObservation,
)
from ..ports import ProviderTable
from .identity import content_hash

SHANGHAI = ZoneInfo("Asia/Shanghai")


class _Source(TypedDict):
    provider: str
    source_endpoint: str
    retrieved_at: datetime
    available_at: datetime
    schema_version: str
    source_record_hash: str


def normalize_taxonomy(table: ProviderTable) -> tuple[IndustryTaxonomyObservation, ...]:
    rows = tuple(
        IndustryTaxonomyObservation(
            **_source(table, row, table.received_at),
            taxonomy="SW",
            taxonomy_version="SW2021",
            level="L1",
            industry_code=_text(row, "index_code"),
            industry_name=_text(row, "industry_name"),
            provider_industry_code=_optional_text(row, "industry_code"),
            is_published=_text(row, "is_pub") == "1",
            parent_code=_optional_text(row, "parent_code"),
        )
        for row in table.rows
        if _text(row, "level") == "L1" and _text(row, "src") == "SW2021"
    )
    indexed = {row.industry_code: row for row in rows}
    if not rows or len(indexed) != len(rows):
        raise ValueError("SW2021 一级行业分类为空或代码重复")
    return tuple(indexed[key] for key in sorted(indexed))


def normalize_memberships(
    table: ProviderTable, *, industry_code: str, industry_name: str, is_current: bool
) -> tuple[IndustryMembershipObservation, ...]:
    rows = []
    for raw in table.rows:
        start, end = _date(raw, "in_date"), _optional_date(raw, "out_date")
        if end is not None and end <= start:
            raise ValueError(f"行业成员区间无效：{industry_code}:{_text(raw, 'ts_code')}")
        rows.append(
            IndustryMembershipObservation(
                **_source(table, raw, datetime.combine(start, time(18), tzinfo=SHANGHAI)),
                taxonomy="SW",
                taxonomy_version="SW2021",
                level="L1",
                industry_code=industry_code,
                industry_name=industry_name,
                instrument_id=_text(raw, "ts_code"),
                instrument_name=_text(raw, "name"),
                effective_from=start,
                effective_to=end,
                is_current=is_current,
            )
        )
    indexed = {
        (row.industry_code, row.instrument_id, row.effective_from, row.effective_to): row
        for row in rows
    }
    return tuple(indexed[key] for key in sorted(indexed, key=str))


def normalize_index_daily(
    table: ProviderTable, *, industry_name: str
) -> tuple[IndustryIndexDailyObservation, ...]:
    rows = tuple(
        IndustryIndexDailyObservation(
            **_source(
                table, raw, datetime.combine(_date(raw, "trade_date"), time(18), tzinfo=SHANGHAI)
            ),
            taxonomy="SW",
            taxonomy_version="SW2021",
            level="L1",
            industry_code=_text(raw, "ts_code"),
            industry_name=industry_name,
            trade_date=_date(raw, "trade_date"),
            open=_float(raw, "open"),
            high=_float(raw, "high"),
            low=_float(raw, "low"),
            close=_float(raw, "close"),
            change=_optional_float(raw, "change"),
            percent_change=_optional_float(raw, "pct_change"),
            volume_provider_native=_optional_float(raw, "vol"),
            amount_provider_native=_optional_float(raw, "amount"),
            price_earnings=_optional_float(raw, "pe"),
            price_book=_optional_float(raw, "pb"),
            float_market_value_provider_native=_optional_float(raw, "float_mv"),
            total_market_value_provider_native=_optional_float(raw, "total_mv"),
        )
        for raw in table.rows
    )
    for row in rows:
        if min(row.open, row.high, row.low, row.close) <= 0:
            raise ValueError("行业指数日线包含非正价格")
        reference = max(row.open, row.high, row.low, row.close)
        tolerance = max(0.01, reference * 0.0001)
        if row.high + tolerance < max(row.open, row.close) or row.low - tolerance > min(
            row.open, row.close
        ):
            raise ValueError("行业指数日线 OHLC 关系无效")
    return tuple(sorted(rows, key=lambda row: (row.trade_date, row.source_record_hash)))


def _source(table: ProviderTable, row: dict[str, object], available_at: datetime) -> _Source:
    return {
        "provider": "tushare",
        "source_endpoint": table.source_endpoint,
        "retrieved_at": table.received_at,
        "available_at": available_at,
        "schema_version": "1.0.0",
        "source_record_hash": content_hash(row),
    }


def _text(row: dict[str, object], field: str) -> str:
    value = str(row.get(field, "")).strip()
    if not value:
        raise ValueError(f"缺少行业字段：{field}")
    return value


def _optional_text(row: dict[str, object], field: str) -> str | None:
    if row.get(field) is None:
        return None
    value = str(row.get(field, "")).strip()
    return value or None


def _date(row: dict[str, object], field: str) -> date:
    return datetime.strptime(_text(row, field), "%Y%m%d").date()


def _optional_date(row: dict[str, object], field: str) -> date | None:
    return _date(row, field) if row.get(field) not in (None, "") else None


def _float(row: dict[str, object], field: str) -> float:
    value = _optional_float(row, field)
    if value is None:
        raise ValueError(f"缺少行业数值字段：{field}")
    return value


def _optional_float(row: dict[str, object], field: str) -> float | None:
    value = row.get(field)
    if value in (None, ""):
        return None
    if not isinstance(value, (int, float, str)):
        raise ValueError(f"无效行业数值字段：{field}")
    return float(value)


__all__ = ["normalize_index_daily", "normalize_memberships", "normalize_taxonomy"]
