"""Normalize Tushare broad-index daily bars with explicit units."""

from __future__ import annotations

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from ..contracts import BroadIndexDailyObservation
from ..ports import ProviderTable
from .identity import content_hash

SHANGHAI = ZoneInfo("Asia/Shanghai")
BROAD_INDEX_REGISTRY = {
    "000001.SH": "上证指数",
    "399001.SZ": "深证成指",
    "399006.SZ": "创业板指",
    "000688.SH": "科创50",
    "000300.SH": "沪深300",
    "000852.SH": "中证1000",
}
INDEX_DAILY_FIELDS = (
    "ts_code",
    "trade_date",
    "close",
    "open",
    "high",
    "low",
    "pre_close",
    "change",
    "pct_chg",
    "vol",
    "amount",
)


def normalize_broad_index_daily(
    table: ProviderTable,
) -> tuple[BroadIndexDailyObservation, ...]:
    rows = []
    for raw in table.rows:
        code = _text(raw, "ts_code")
        if code not in BROAD_INDEX_REGISTRY:
            raise ValueError(f"宽基指数不在注册表：{code}")
        ohlc = tuple(raw.get(name) for name in ("open", "high", "low", "close"))
        if all(value in (None, "") for value in ohlc) or (
            all(raw.get(name) in (None, "") for name in ("open", "high", "low"))
            and raw.get("pre_close") in (None, "")
        ):
            continue
        if any(value in (None, "") for value in ohlc):
            raise ValueError(f"宽基指数 OHLC 部分缺失：{code}:{raw.get('trade_date')}")
        trade_date = _date(raw, "trade_date")
        values = {name: _float(raw, name) for name in ("open", "high", "low", "close")}
        if min(values.values()) <= 0:
            raise ValueError(f"宽基指数包含非正价格：{code}:{trade_date}")
        if values["high"] < max(values["open"], values["close"]):
            raise ValueError(f"宽基指数最高价关系无效：{code}:{trade_date}")
        if values["low"] > min(values["open"], values["close"]):
            raise ValueError(f"宽基指数最低价关系无效：{code}:{trade_date}")
        rows.append(
            BroadIndexDailyObservation(
                provider=table.provider_id,
                source_endpoint=table.source_endpoint,
                retrieved_at=table.received_at,
                available_at=datetime.combine(trade_date, time(18), tzinfo=SHANGHAI),
                schema_version="1.0.0",
                source_record_hash=content_hash(raw),
                registry_version="a-share-broad-index-v1",
                instrument_id=code,
                instrument_name=BROAD_INDEX_REGISTRY[code],
                trade_date=trade_date,
                open=values["open"],
                high=values["high"],
                low=values["low"],
                close=values["close"],
                previous_close=_float(raw, "pre_close"),
                change=_float(raw, "change"),
                percent_change=_float(raw, "pct_chg"),
                volume_lots=_float(raw, "vol"),
                amount_cny=_float(raw, "amount") * 1000,
            )
        )
    identities = {(row.instrument_id, row.trade_date) for row in rows}
    if len(identities) != len(rows):
        raise ValueError("宽基指数日线包含重复身份")
    return tuple(sorted(rows, key=lambda row: (row.instrument_id, row.trade_date)))


def _text(row: dict[str, object], field: str) -> str:
    value = str(row.get(field, "")).strip()
    if not value:
        raise ValueError(f"缺少宽基指数字段：{field}")
    return value


def _date(row: dict[str, object], field: str) -> date:
    return datetime.strptime(_text(row, field), "%Y%m%d").date()


def _float(row: dict[str, object], field: str) -> float:
    value = row.get(field)
    if value in (None, ""):
        raise ValueError(f"缺少宽基指数数值字段：{field}")
    if not isinstance(value, (int, float, str)):
        raise ValueError(f"宽基指数数值字段无效：{field}")
    return float(value)


__all__ = [
    "BROAD_INDEX_REGISTRY",
    "INDEX_DAILY_FIELDS",
    "normalize_broad_index_daily",
]
