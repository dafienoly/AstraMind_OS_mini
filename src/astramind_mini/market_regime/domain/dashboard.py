"""Pure descriptive classification for the market dashboard."""

from __future__ import annotations

from typing import Literal

from ..contracts.dashboard import MarketRegimeEvidence

PROJECTION_VERSION = "market-dashboard-v1.0.0"
REGIME_VERSION = "market-regime-breadth-price-v1.0.0"


def describe_regime(
    *,
    index_return_20d: float | None,
    advance_ratio: float,
    amount_change_20d: float | None,
) -> MarketRegimeEvidence:
    if index_return_20d is None:
        return MarketRegimeEvidence(
            state="unknown",
            label="趋势历史不足",
            confidence=0.0,
            definition_version=REGIME_VERSION,
            observations=("宽基指数不足 20 个交易日",),
        )
    price_positive = index_return_20d > 0.02
    price_negative = index_return_20d < -0.02
    breadth_positive = advance_ratio >= 0.56
    breadth_negative = advance_ratio <= 0.44
    liquidity_positive = amount_change_20d is not None and amount_change_20d > 0.08
    if price_positive and breadth_positive:
        state: Literal["strong", "balanced", "weak", "divergent", "unknown"] = "strong"
        label = "价格与参与同步增强"
    elif price_negative and breadth_negative:
        state, label = "weak", "价格与参与同步减弱"
    elif price_positive != breadth_positive and (price_positive or breadth_negative):
        state, label = "divergent", "价格与市场广度分歧"
    else:
        state, label = "balanced", "结构均衡，方向尚未集中"
    agreements = sum(
        (
            price_positive and breadth_positive,
            price_negative and breadth_negative,
            liquidity_positive and price_positive,
        )
    )
    confidence = min(0.95, 0.45 + agreements * 0.16)
    observations = (
        f"沪深300近20日 {index_return_20d:+.2%}",
        f"上涨家数占比 {advance_ratio:.1%}",
        "成交额较20日均值 "
        + ("不可用" if amount_change_20d is None else f"{amount_change_20d:+.1%}"),
    )
    return MarketRegimeEvidence(
        state=state,
        label=label,
        confidence=confidence,
        definition_version=REGIME_VERSION,
        observations=observations,
    )


__all__ = ["PROJECTION_VERSION", "REGIME_VERSION", "describe_regime"]
