"""First three deterministic tactical strategy families."""

from __future__ import annotations

from collections.abc import Sequence
from statistics import median

from ..domain.backtest_models import CandidateSignal, ResearchBar


def event_attention_signal(
    history: Sequence[ResearchBar],
    horizon_sessions: int,
) -> CandidateSignal | None:
    if len(history) < 21:
        return None
    latest = history[-1]
    baseline = median(bar.amount_cny for bar in history[-21:-1])
    amount_ratio = latest.amount_cny / baseline if baseline > 0 else 0.0
    daily_return = latest.research_close_index / history[-2].research_close_index - 1
    limit_attention = bool(latest.upper_limit_locked or latest.lower_limit_locked)
    if amount_ratio < 1.8 or (abs(daily_return) < 0.03 and not limit_attention):
        return None
    score = min(amount_ratio, 5.0) + abs(daily_return) * 10 + int(limit_attention)
    return _signal(
        latest,
        "event_attention",
        horizon_sessions,
        score,
        (f"amount_ratio={amount_ratio:.2f}", f"daily_return={daily_return:.4f}"),
    )


def momentum_breakout_signal(
    history: Sequence[ResearchBar],
    horizon_sessions: int,
) -> CandidateSignal | None:
    if len(history) < 21:
        return None
    latest = history[-1]
    prior = history[-21:-1]
    prior_high = max(bar.research_close_index for bar in prior)
    amount_median = median(bar.amount_cny for bar in prior)
    strength = latest.research_close_index / prior_high - 1
    amount_ratio = latest.amount_cny / amount_median if amount_median > 0 else 0.0
    if strength <= 0 or amount_ratio < 1.1:
        return None
    return _signal(
        latest,
        "momentum_breakout",
        horizon_sessions,
        strength * 100 + min(amount_ratio, 3),
        (f"breakout={strength:.4f}", f"amount_ratio={amount_ratio:.2f}"),
    )


def reversal_volume_price_signal(
    history: Sequence[ResearchBar],
    horizon_sessions: int,
) -> CandidateSignal | None:
    if len(history) < 21:
        return None
    latest = history[-1]
    five_day_return = latest.research_close_index / history[-6].research_close_index - 1
    daily_return = latest.research_close_index / history[-2].research_close_index - 1
    amount_median = median(bar.amount_cny for bar in history[-21:-1])
    amount_ratio = latest.amount_cny / amount_median if amount_median > 0 else 0.0
    if five_day_return > -0.08 or daily_return <= 0 or amount_ratio > 1.5:
        return None
    return _signal(
        latest,
        "reversal_volume_price",
        horizon_sessions,
        abs(five_day_return) * 100 + daily_return * 20 + max(0, 1.5 - amount_ratio),
        (f"return_5d={five_day_return:.4f}", f"daily_rebound={daily_return:.4f}"),
    )


def _signal(
    latest: ResearchBar,
    family: str,
    horizon_sessions: int,
    score: float,
    reasons: tuple[str, ...],
) -> CandidateSignal:
    if horizon_sessions not in {2, 5, 10}:
        raise ValueError("首批策略周期只能为 2/5/10 个交易日")
    return CandidateSignal(
        instrument_id=latest.instrument_id,
        signal_date=latest.trade_date,
        family=family,
        horizon_sessions=horizon_sessions,
        score=score,
        reasons=reasons,
    )


__all__ = [
    "event_attention_signal",
    "momentum_breakout_signal",
    "reversal_volume_price_signal",
]
