"""Point-in-time tactical-universe decisions."""

from __future__ import annotations

from collections.abc import Sequence
from statistics import median

from ..domain.backtest_models import (
    ResearchBar,
    UniverseDecision,
    UniverseRules,
)


def evaluate_universe(
    history: Sequence[ResearchBar],
    rules: UniverseRules,
    *,
    event_attention: bool = False,
) -> UniverseDecision:
    if not history:
        raise ValueError("股票池判断需要至少一个当时可见 Bar")
    latest = history[-1]
    amounts = [bar.amount_cny for bar in history[-20:] if bar.has_daily_bar]
    amount_median = median(amounts) if amounts else 0.0
    reasons: list[str] = []
    if latest.listed_sessions < rules.minimum_listed_sessions:
        reasons.append("seasoning")
    if latest.risk_status != "normal":
        reasons.append("special_treatment_or_unknown")
    if not latest.has_daily_bar:
        reasons.append("missing_bar")
    if latest.buy_state != "tradable" or latest.sell_state != "tradable":
        reasons.append("not_two_way_tradable")
    if amount_median < rules.minimum_median_amount_20d_cny:
        reasons.append("insufficient_liquidity")
    eligible = not reasons
    event_reasons = set(reasons) - {"insufficient_liquidity"}
    event_channel = (
        event_attention
        and rules.allow_event_coverage_channel
        and not event_reasons
        and amount_median > 0
    )
    return UniverseDecision(
        instrument_id=latest.instrument_id,
        as_of=latest.trade_date,
        eligible=eligible,
        event_channel_eligible=event_channel,
        reasons=tuple(reasons),
    )


__all__ = ["evaluate_universe"]
