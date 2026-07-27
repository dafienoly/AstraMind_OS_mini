"""Point-in-time conservative normalization for WP-0002B datasets."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import date, datetime
from typing import Any, Literal, cast

from ..application.identity import content_hash
from ..contracts import (
    AdjustmentFactorObservation,
    DailyBarObservation,
    DailyBasicObservation,
    PriceLimitObservation,
    SecurityMasterObservation,
    SuspensionEventObservation,
    TradeCalendarObservation,
)
from ..ports import ProviderTable

type NormalizedObservation = (
    SecurityMasterObservation
    | TradeCalendarObservation
    | DailyBarObservation
    | AdjustmentFactorObservation
    | DailyBasicObservation
    | PriceLimitObservation
    | SuspensionEventObservation
)


def normalize_security_master(
    tables: Sequence[ProviderTable],
) -> tuple[SecurityMasterObservation, ...]:
    rows = [
        SecurityMasterObservation(
            **_source(table, row),
            instrument_id=_required_text(row, "ts_code"),
            symbol=_required_text(row, "symbol"),
            name=_required_text(row, "name"),
            area=_optional_text(row, "area"),
            industry=_optional_text(row, "industry"),
            market=_optional_text(row, "market"),
            exchange=_required_text(row, "exchange"),
            currency=_required_text(row, "curr_type"),
            list_status=_list_status(row),
            list_date=_optional_date(row, "list_date"),
            delist_date=_optional_date(row, "delist_date"),
            connect_flag=_optional_text(row, "is_hs"),
        )
        for table in tables
        for row in table.rows
    ]
    return _deduplicate(rows, lambda item: item.instrument_id)


def normalize_trade_calendar(
    tables: Sequence[ProviderTable],
) -> tuple[TradeCalendarObservation, ...]:
    rows = [
        TradeCalendarObservation(
            **_source(table, row),
            exchange=_required_text(row, "exchange"),
            calendar_date=_required_date(row, "cal_date"),
            is_open=_required_text(row, "is_open") == "1",
            previous_trade_date=_optional_date(row, "pretrade_date"),
        )
        for table in tables
        for row in table.rows
    ]
    return _deduplicate(rows, lambda item: f"{item.exchange}:{item.calendar_date}")


def normalize_daily_bars(table: ProviderTable) -> tuple[DailyBarObservation, ...]:
    rows = tuple(
        DailyBarObservation(
            **_source(table, row),
            instrument_id=_required_text(row, "ts_code"),
            trade_date=_required_date(row, "trade_date"),
            open=_required_float(row, "open"),
            high=_required_float(row, "high"),
            low=_required_float(row, "low"),
            close=_required_float(row, "close"),
            previous_close=_required_float(row, "pre_close"),
            change=_required_float(row, "change"),
            percent_change=_required_float(row, "pct_chg"),
            volume_lots=_required_float(row, "vol"),
            amount_thousand_cny=_required_float(row, "amount"),
        )
        for row in table.rows
    )
    for row in rows:
        if row.low > min(row.open, row.close) or row.high < max(row.open, row.close):
            raise ValueError(f"{row.instrument_id} OHLC 关系无效")
        if row.high < row.low or row.volume_lots < 0 or row.amount_thousand_cny < 0:
            raise ValueError(f"{row.instrument_id} 行情数值无效")
    return _deduplicate(rows, lambda item: f"{item.instrument_id}:{item.trade_date}")


def normalize_adjustment_factors(
    table: ProviderTable,
) -> tuple[AdjustmentFactorObservation, ...]:
    rows = tuple(
        AdjustmentFactorObservation(
            **_source(table, row),
            instrument_id=_required_text(row, "ts_code"),
            trade_date=_required_date(row, "trade_date"),
            adjustment_factor=_required_float(row, "adj_factor"),
        )
        for row in table.rows
    )
    if any(row.adjustment_factor <= 0 for row in rows):
        raise ValueError("复权因子必须为正数")
    return _deduplicate(rows, lambda item: f"{item.instrument_id}:{item.trade_date}")


def normalize_daily_basic(table: ProviderTable) -> tuple[DailyBasicObservation, ...]:
    rows = tuple(
        DailyBasicObservation(
            **_source(table, row),
            instrument_id=_required_text(row, "ts_code"),
            trade_date=_required_date(row, "trade_date"),
            close=_required_float(row, "close"),
            turnover_rate=_optional_float(row, "turnover_rate"),
            turnover_rate_free_float=_optional_float(row, "turnover_rate_f"),
            volume_ratio=_optional_float(row, "volume_ratio"),
            price_earnings=_optional_float(row, "pe"),
            price_earnings_ttm=_optional_float(row, "pe_ttm"),
            price_book=_optional_float(row, "pb"),
            price_sales=_optional_float(row, "ps"),
            price_sales_ttm=_optional_float(row, "ps_ttm"),
            dividend_yield=_optional_float(row, "dv_ratio"),
            dividend_yield_ttm=_optional_float(row, "dv_ttm"),
            total_shares_ten_thousand=_optional_float(row, "total_share"),
            float_shares_ten_thousand=_optional_float(row, "float_share"),
            free_float_shares_ten_thousand=_optional_float(row, "free_share"),
            total_market_value_ten_thousand_cny=_optional_float(row, "total_mv"),
            circulating_market_value_ten_thousand_cny=_optional_float(row, "circ_mv"),
        )
        for row in table.rows
    )
    if any(row.close <= 0 or _daily_basic_has_negative_scale(row) for row in rows):
        raise ValueError("每日指标包含无效价格、换手、股本或市值")
    return _deduplicate(rows, lambda item: f"{item.instrument_id}:{item.trade_date}")


def normalize_price_limits(table: ProviderTable) -> tuple[PriceLimitObservation, ...]:
    rows = tuple(
        PriceLimitObservation(
            **_source(table, row),
            instrument_id=_required_text(row, "ts_code"),
            trade_date=_required_date(row, "trade_date"),
            previous_close=_optional_float(row, "pre_close"),
            upper_limit=_required_float(row, "up_limit"),
            lower_limit=_required_float(row, "down_limit"),
            limit_prices_usable=_limit_prices_usable(row),
        )
        for row in table.rows
    )
    return _deduplicate(rows, lambda item: f"{item.instrument_id}:{item.trade_date}")


def normalize_suspension_events(
    table: ProviderTable,
) -> tuple[SuspensionEventObservation, ...]:
    rows = tuple(
        SuspensionEventObservation(
            **_source(table, row),
            instrument_id=_required_text(row, "ts_code"),
            trade_date=_required_date(row, "trade_date"),
            suspension_timing=_optional_text(row, "suspend_timing"),
            suspension_type=_suspension_type(row),
        )
        for row in table.rows
    )
    return _deduplicate(
        rows,
        lambda item: (
            f"{item.instrument_id}:{item.trade_date}:"
            f"{item.suspension_type}:{item.suspension_timing or ''}"
        ),
    )


def _source(table: ProviderTable, row: dict[str, object]) -> dict[str, Any]:
    return {
        "provider": "tushare",
        "source_endpoint": table.source_endpoint,
        "retrieved_at": table.received_at,
        "available_at": table.received_at,
        "schema_version": "1.0.0",
        "source_record_hash": content_hash(row),
    }


def _deduplicate[T: NormalizedObservation](
    rows: Sequence[T],
    key: Callable[[T], str],
) -> tuple[T, ...]:
    indexed: dict[str, T] = {}
    for row in rows:
        identity = key(row)
        existing = indexed.get(identity)
        if existing is not None and existing != row:
            raise ValueError(f"标准化主键冲突：{identity}")
        indexed[identity] = row
    return tuple(indexed[name] for name in sorted(indexed))


def _required_text(row: dict[str, object], field: str) -> str:
    value = str(row.get(field, "")).strip()
    if not value:
        raise ValueError(f"缺少必填字段：{field}")
    return value


def _optional_text(row: dict[str, object], field: str) -> str | None:
    raw_value = row.get(field)
    if raw_value is None:
        return None
    value = str(raw_value).strip()
    return value or None


def _list_status(row: dict[str, object]) -> Literal["L", "D", "P"]:
    value = _required_text(row, "list_status")
    if value not in {"L", "D", "P"}:
        raise ValueError(f"未知上市状态：{value}")
    return cast(Literal["L", "D", "P"], value)


def _required_date(row: dict[str, object], field: str) -> date:
    return datetime.strptime(_required_text(row, field), "%Y%m%d").date()


def _optional_date(row: dict[str, object], field: str) -> date | None:
    value = _optional_text(row, field)
    return datetime.strptime(value, "%Y%m%d").date() if value else None


def _required_float(row: dict[str, object], field: str) -> float:
    value = row.get(field)
    if value is None or value == "":
        raise ValueError(f"缺少必填字段：{field}")
    if not isinstance(value, (int, float, str)):
        raise ValueError(f"字段不是数值：{field}")
    return float(value)


def _optional_float(row: dict[str, object], field: str) -> float | None:
    value = row.get(field)
    if value is None or value == "":
        return None
    if not isinstance(value, (int, float, str)):
        raise ValueError(f"字段不是数值：{field}")
    return float(value)


def _daily_basic_has_negative_scale(row: DailyBasicObservation) -> bool:
    values = (
        row.turnover_rate,
        row.turnover_rate_free_float,
        row.total_shares_ten_thousand,
        row.float_shares_ten_thousand,
        row.free_float_shares_ten_thousand,
        row.total_market_value_ten_thousand_cny,
        row.circulating_market_value_ten_thousand_cny,
    )
    return any(value is not None and value < 0 for value in values)


def _limit_prices_usable(row: dict[str, object]) -> bool:
    upper = _required_float(row, "up_limit")
    lower = _required_float(row, "down_limit")
    return upper > 0 and lower > 0 and upper >= lower


def _suspension_type(row: dict[str, object]) -> Literal["S", "R"]:
    value = _required_text(row, "suspend_type")
    if value not in {"S", "R"}:
        raise ValueError(f"未知停复牌类型：{value}")
    return cast(Literal["S", "R"], value)


__all__ = [
    "normalize_adjustment_factors",
    "normalize_daily_bars",
    "normalize_daily_basic",
    "normalize_price_limits",
    "normalize_security_master",
    "normalize_suspension_events",
    "normalize_trade_calendar",
]
