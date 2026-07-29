"""Point-in-time normalization for daily reference datasets."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, datetime, time
from typing import Any, Literal, cast
from zoneinfo import ZoneInfo

from ..contracts import CorporateActionObservation, SecurityNameHistoryObservation
from ..ports import ProviderTable
from .identity import content_hash

SHANGHAI = ZoneInfo("Asia/Shanghai")

NAME_CHANGE_FIELDS = (
    "ts_code",
    "name",
    "start_date",
    "end_date",
    "ann_date",
    "change_reason",
)
DIVIDEND_FIELDS = (
    "ts_code",
    "end_date",
    "ann_date",
    "div_proc",
    "stk_div",
    "stk_bo_rate",
    "stk_co_rate",
    "cash_div",
    "cash_div_tax",
    "record_date",
    "ex_date",
    "pay_date",
    "div_listdate",
    "imp_ann_date",
    "base_date",
    "base_share",
)


def normalize_name_history(
    tables: Sequence[ProviderTable],
) -> tuple[SecurityNameHistoryObservation, ...]:
    staged: dict[tuple[str, date, str], tuple[ProviderTable, Mapping[str, Any]]] = {}
    for table in tables:
        for row in table.rows:
            instrument = _text(row, "ts_code")
            name = _text(row, "name")
            start = _date(row, "start_date")
            staged[(instrument, start, name)] = (table, row)
    grouped: dict[str, list[tuple[date, str, ProviderTable, Mapping[str, Any]]]] = {}
    for (instrument, start, name), (source_table, source_row) in staged.items():
        grouped.setdefault(instrument, []).append((start, name, source_table, source_row))
    result = []
    for instrument, items in grouped.items():
        ordered = sorted(items, key=lambda item: (item[0], item[1]))
        for index, (start, name, source_table, source_row) in enumerate(ordered):
            provider_end = _optional_date(source_row, "end_date")
            next_start = ordered[index + 1][0] if index + 1 < len(ordered) else None
            computed_end = (
                next_start
                if next_start and (not provider_end or next_start < provider_end)
                else provider_end
            )
            announced = _optional_date(source_row, "ann_date")
            reason = str(source_row.get("change_reason") or "").strip()
            risk = _risk_status(name, reason)
            available_at = (
                datetime.combine(announced, time(18), tzinfo=SHANGHAI)
                if announced
                else source_table.received_at
            )
            result.append(
                SecurityNameHistoryObservation(
                    provider=source_table.provider_id,
                    source_endpoint=source_table.source_endpoint,
                    retrieved_at=source_table.received_at,
                    available_at=available_at,
                    schema_version="1.1.0",
                    source_record_hash=content_hash(dict(source_row)),
                    instrument_id=instrument,
                    name=name,
                    effective_start_date=start,
                    effective_end_date=computed_end,
                    provider_end_date=provider_end,
                    announced_on=announced,
                    change_reason=reason,
                    risk_status=risk,
                    is_special_treatment=risk != "normal",
                )
            )
    return tuple(result)


def normalize_corporate_actions(
    tables: Sequence[ProviderTable],
) -> tuple[CorporateActionObservation, ...]:
    result: dict[str, CorporateActionObservation] = {}
    for table in tables:
        for row in table.rows:
            digest = content_hash(dict(row))
            announced = _optional_date(row, "ann_date")
            implementation_announced = _optional_date(row, "imp_ann_date")
            latest_announcement = (
                max(value for value in (announced, implementation_announced) if value is not None)
                if announced or implementation_announced
                else None
            )
            available_at = (
                datetime.combine(latest_announcement, time(18), tzinfo=SHANGHAI)
                if latest_announcement
                else table.received_at
            )
            stock_total = _optional_float(row, "stk_div")
            stock = (
                stock_total
                if stock_total is not None
                else sum(
                    value or 0.0
                    for value in (
                        _optional_float(row, "stk_bo_rate"),
                        _optional_float(row, "stk_co_rate"),
                    )
                )
            )
            cash = _optional_float(row, "cash_div")
            result[digest] = CorporateActionObservation(
                provider=table.provider_id,
                source_endpoint=table.source_endpoint,
                retrieved_at=table.received_at,
                available_at=available_at,
                schema_version="1.1.0",
                source_record_hash=digest,
                instrument_id=_text(row, "ts_code"),
                reporting_period=_date(row, "end_date"),
                announced_on=announced,
                availability_known=latest_announcement is not None,
                process_status=str(row.get("div_proc") or "").strip() or "unknown",
                action_kind=_action_kind(stock, cash),
                stock_dividend_per_share=stock or None,
                cash_dividend_pre_tax_per_share=cash,
                cash_dividend_after_tax_per_share=_optional_float(row, "cash_div_tax"),
                record_date=_optional_date(row, "record_date"),
                ex_date=_optional_date(row, "ex_date"),
                payment_date=_optional_date(row, "pay_date"),
                base_date=_optional_date(row, "base_date"),
                base_shares_ten_thousand=_optional_float(row, "base_share"),
                provider_record_hash=digest,
                is_implemented=bool(
                    _optional_date(row, "imp_ann_date") or _optional_date(row, "ex_date")
                ),
            )
    return tuple(result.values())


def _risk_status(name: str, reason: str) -> Literal["normal", "st", "star_st", "pt", "high_risk"]:
    upper = name.upper()
    if upper.startswith("*ST"):
        return "star_st"
    if upper.startswith("ST") or upper.startswith("SST"):
        return "st"
    if upper.startswith("PT"):
        return "pt"
    if "特别处理" in reason or "退市风险" in reason:
        return "high_risk"
    return "normal"


def _action_kind(
    stock: float, cash: float | None
) -> Literal["cash", "stock", "cash_and_stock", "unspecified"]:
    if stock and cash:
        return "cash_and_stock"
    if stock:
        return "stock"
    if cash:
        return "cash"
    return "unspecified"


def _text(row: Mapping[str, Any], key: str) -> str:
    value = str(row.get(key) or "").strip()
    if not value:
        raise ValueError(f"{key} 不能为空")
    return value


def _date(row: Mapping[str, Any], key: str) -> date:
    value = _optional_date(row, key)
    if value is None:
        raise ValueError(f"{key} 不能为空")
    return value


def _optional_date(row: Mapping[str, Any], key: str) -> date | None:
    value = str(row.get(key) or "").strip()
    return datetime.strptime(value, "%Y%m%d").date() if value else None


def _optional_float(row: Mapping[str, Any], key: str) -> float | None:
    value = row.get(key)
    return float(cast(Any, value)) if value not in (None, "") else None


__all__ = [
    "DIVIDEND_FIELDS",
    "NAME_CHANGE_FIELDS",
    "normalize_corporate_actions",
    "normalize_name_history",
]
