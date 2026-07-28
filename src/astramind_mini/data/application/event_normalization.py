"""Point-in-time normalization for tactical event datasets."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import date, datetime, time
from typing import Literal, TypedDict, cast
from zoneinfo import ZoneInfo

from ..contracts import (
    LhbEventObservation,
    LhbSeatObservation,
    ShareholderCountObservation,
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


def normalize_lhb_events(table: ProviderTable) -> tuple[LhbEventObservation, ...]:
    rows = tuple(
        LhbEventObservation(
            **_source(table, row, _required_date(row, "trade_date")),
            instrument_id=_required_text(row, "ts_code"),
            trade_date=_required_date(row, "trade_date"),
            name=_required_text(row, "name"),
            close=_optional_float(row, "close"),
            percent_change=_optional_float(row, "pct_change"),
            turnover_rate=_optional_float(row, "turnover_rate"),
            amount_ten_thousand_cny=_optional_float(row, "amount"),
            list_sell_ten_thousand_cny=_optional_float(row, "l_sell"),
            list_buy_ten_thousand_cny=_optional_float(row, "l_buy"),
            list_amount_ten_thousand_cny=_optional_float(row, "l_amount"),
            net_amount_ten_thousand_cny=_optional_float(row, "net_amount"),
            net_rate=_optional_float(row, "net_rate"),
            amount_rate=_optional_float(row, "amount_rate"),
            float_value_ten_thousand_cny=_optional_float(row, "float_values"),
            reason=_required_text(row, "reason"),
        )
        for row in table.rows
    )
    if any(
        (row.close is not None and row.close <= 0)
        or (row.amount_ten_thousand_cny is not None and row.amount_ten_thousand_cny < 0)
        for row in rows
    ):
        raise ValueError("龙虎榜事件包含无效价格或成交额")
    return _deduplicate(rows, lambda row: row.source_record_hash)


def normalize_lhb_seats(table: ProviderTable) -> tuple[LhbSeatObservation, ...]:
    rows = tuple(
        LhbSeatObservation(
            **_source(table, row, _required_date(row, "trade_date")),
            instrument_id=_required_text(row, "ts_code"),
            trade_date=_required_date(row, "trade_date"),
            seat_name=_required_text(row, "exalter"),
            side=_side(row),
            buy_cny=_optional_float(row, "buy"),
            buy_rate=_optional_float(row, "buy_rate"),
            sell_cny=_optional_float(row, "sell"),
            sell_rate=_optional_float(row, "sell_rate"),
            net_buy_cny=_optional_float(row, "net_buy"),
            reason=_required_text(row, "reason"),
        )
        for row in table.rows
    )
    if any(
        (row.buy_cny is not None and row.buy_cny < 0)
        or (row.sell_cny is not None and row.sell_cny < 0)
        for row in rows
    ):
        raise ValueError("龙虎榜席位包含负买卖金额")
    return _deduplicate(rows, lambda row: row.source_record_hash)


def normalize_shareholder_counts(
    table: ProviderTable,
) -> tuple[ShareholderCountObservation, ...]:
    rows = tuple(
        ShareholderCountObservation(
            **_source(
                table,
                row,
                max(_required_date(row, "ann_date"), _required_date(row, "end_date")),
            ),
            instrument_id=_required_text(row, "ts_code"),
            announced_on=_required_date(row, "ann_date"),
            reporting_period=_required_date(row, "end_date"),
            holder_count=_optional_int(row, "holder_num"),
        )
        for row in table.rows
    )
    if any(row.holder_count is not None and row.holder_count <= 0 for row in rows):
        raise ValueError("股东户数包含无效数量")
    return _deduplicate(rows, lambda row: row.source_record_hash)


def _source(table: ProviderTable, row: dict[str, object], available_date: date) -> _Source:
    return {
        "provider": "tushare",
        "source_endpoint": table.source_endpoint,
        "retrieved_at": table.received_at,
        "available_at": datetime.combine(available_date, time(18), tzinfo=SHANGHAI),
        "schema_version": "1.0.0",
        "source_record_hash": content_hash(row),
    }


def _deduplicate[T](
    rows: Sequence[T],
    key: Callable[[T], str],
) -> tuple[T, ...]:
    indexed: dict[str, T] = {}
    for row in rows:
        identity = key(row)
        existing = indexed.get(identity)
        if existing is not None and existing != row:
            raise ValueError(f"事件标准化身份冲突：{identity}")
        indexed[identity] = row
    return tuple(indexed[name] for name in sorted(indexed))


def _required_text(row: dict[str, object], field: str) -> str:
    value = str(row.get(field, "")).strip()
    if not value:
        raise ValueError(f"缺少必填字段：{field}")
    return value


def _required_date(row: dict[str, object], field: str) -> date:
    return datetime.strptime(_required_text(row, field), "%Y%m%d").date()


def _required_float(row: dict[str, object], field: str) -> float:
    value = row.get(field)
    if value is None or value == "" or not isinstance(value, (int, float, str)):
        raise ValueError(f"缺少或无效数值字段：{field}")
    return float(value)


def _optional_float(row: dict[str, object], field: str) -> float | None:
    value = row.get(field)
    if value is None or value == "":
        return None
    if not isinstance(value, (int, float, str)):
        raise ValueError(f"无效数值字段：{field}")
    return float(value)


def _required_int(row: dict[str, object], field: str) -> int:
    value = _required_float(row, field)
    if not value.is_integer():
        raise ValueError(f"字段不是整数：{field}")
    return int(value)


def _optional_int(row: dict[str, object], field: str) -> int | None:
    if row.get(field) in (None, ""):
        return None
    return _required_int(row, field)


def _side(row: dict[str, object]) -> Literal["0", "1"]:
    value = _required_text(row, "side")
    if value not in {"0", "1"}:
        raise ValueError(f"未知席位买卖类型：{value}")
    return cast(Literal["0", "1"], value)


__all__ = [
    "normalize_lhb_events",
    "normalize_lhb_seats",
    "normalize_shareholder_counts",
]
