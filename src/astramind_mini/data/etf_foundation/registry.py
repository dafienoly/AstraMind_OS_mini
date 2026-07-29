"""Versioned SW2021 L1 to ETF research mapping."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal

MAPPING_VERSION = "sw2021-l1-etf-mapping-v1.0.0"
MAPPING_EFFECTIVE_FROM = date(2026, 7, 29)

Tier = Literal[
    "exact",
    "subindustry",
    "composite_proxy",
    "theme_context",
    "unavailable",
]


@dataclass(frozen=True, slots=True)
class EtfMappingDefinition:
    industry_code: str
    industry_name: str
    etf_code: str | None
    tier: Tier
    tracked_index: str | None

    @property
    def eligible(self) -> bool:
        return self.tier == "exact"


def _row(
    code: str,
    name: str,
    etf: str | None = None,
    tier: Tier = "unavailable",
    tracked: str | None = None,
) -> EtfMappingDefinition:
    return EtfMappingDefinition(code, name, etf, tier, tracked)


ETF_MAPPINGS = (
    _row("801010.SI", "农林牧渔", "159825.SZ", "exact", "中证农业主题指数"),
    _row("801030.SI", "基础化工", "516020.SH", "exact", "中证细分化工产业主题指数"),
    _row("801040.SI", "钢铁", "515210.SH", "exact", "中证钢铁指数"),
    _row("801050.SI", "有色金属", "512400.SH", "exact", "中证申万有色金属指数"),
    _row("801080.SI", "电子", "159997.SZ", "composite_proxy", "中证电子指数"),
    _row("801080.SI", "电子", "512480.SH", "subindustry", "中证全指半导体产品与设备指数"),
    _row("801110.SI", "家用电器", "159996.SZ", "exact", "中证全指家用电器指数"),
    _row("801120.SI", "食品饮料", "515170.SH", "exact", "中证细分食品饮料产业主题指数"),
    _row("801130.SI", "纺织服饰", "159928.SZ", "theme_context", "中证主要消费指数"),
    _row("801140.SI", "轻工制造"),
    _row("801150.SI", "医药生物", "512010.SH", "exact", "沪深300医药卫生指数"),
    _row("801160.SI", "公用事业", "159059.SZ", "composite_proxy", "中证全指电力公用事业指数"),
    _row("801170.SI", "交通运输", "159666.SZ", "exact", "中证全指运输指数"),
    _row("801180.SI", "房地产", "512200.SH", "exact", "中证全指房地产指数"),
    _row("801200.SI", "商贸零售", "159928.SZ", "theme_context", "中证主要消费指数"),
    _row("801210.SI", "社会服务", "159766.SZ", "composite_proxy", "中证旅游主题指数"),
    _row("801230.SI", "综合"),
    _row("801710.SI", "建筑材料", "159745.SZ", "exact", "中证全指建筑材料指数"),
    _row("801720.SI", "建筑装饰", "516950.SH", "composite_proxy", "中证基建工程指数"),
    _row("801730.SI", "电力设备", "516160.SH", "composite_proxy", "中证新能源指数"),
    _row("801740.SI", "国防军工", "512660.SH", "exact", "中证军工指数"),
    _row("801750.SI", "计算机", "159998.SZ", "exact", "中证计算机主题指数"),
    _row("801760.SI", "传媒", "512980.SH", "exact", "中证传媒指数"),
    _row("801770.SI", "通信", "515880.SH", "exact", "中证全指通信设备指数"),
    _row("801780.SI", "银行", "512800.SH", "exact", "中证银行指数"),
    _row("801790.SI", "非银金融", "512880.SH", "composite_proxy", "中证全指证券公司指数"),
    _row("801880.SI", "汽车", "516110.SH", "exact", "中证全指汽车指数"),
    _row("801890.SI", "机械设备", "159886.SZ", "exact", "中证细分机械设备产业主题指数"),
    _row("801950.SI", "煤炭", "515220.SH", "exact", "中证煤炭指数"),
    _row("801960.SI", "石油石化", "561360.SH", "exact", "中证油气产业指数"),
    _row("801970.SI", "环保", "512580.SH", "exact", "中证环保产业指数"),
    _row("801980.SI", "美容护理"),
)

ETF_CODES = tuple(sorted({row.etf_code for row in ETF_MAPPINGS if row.etf_code}))


def validate_registry() -> None:
    identities = {(row.industry_code, row.industry_name) for row in ETF_MAPPINGS}
    if len(identities) != 31:
        raise ValueError(f"ETF 映射必须覆盖 31 个 SW2021 L1，实际 {len(identities)}")
    seen: set[tuple[str, str | None]] = set()
    for row in ETF_MAPPINGS:
        key = row.industry_code, row.etf_code
        if key in seen:
            raise ValueError(f"ETF 映射重复：{key}")
        seen.add(key)
        if row.tier == "unavailable" and row.etf_code is not None:
            raise ValueError(f"不可用映射不得绑定 ETF：{row.industry_code}")
        if row.tier != "unavailable" and row.etf_code is None:
            raise ValueError(f"可用映射缺少 ETF：{row.industry_code}")


__all__ = [
    "ETF_CODES",
    "ETF_MAPPINGS",
    "MAPPING_EFFECTIVE_FROM",
    "MAPPING_VERSION",
    "EtfMappingDefinition",
    "validate_registry",
]
