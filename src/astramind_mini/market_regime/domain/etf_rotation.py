"""Pure ETF rotation research formula and target-draft construction."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from itertools import pairwise
from statistics import median, pstdev

from ..contracts.etf_rotation import (
    CandidateState,
    EtfReplaySummary,
    EtfRotationCandidate,
    EtfTargetDraft,
    EtfTargetWeight,
)
from ..contracts.hierarchy import PriceCandle

STRATEGY_VERSION = "etf-rotation-research-v1.0.0"
SPREAD_PROXY_THRESHOLD_BPS = 35.0
TRACKING_PROXY_THRESHOLD = 0.12
MIN_SESSIONS = 252
MIN_AMOUNT_CNY = 20_000_000.0
MIN_SIZE_CNY = 100_000_000.0
MIN_SCORE = 60.0
MAX_POSITIONS = 2
MAX_WEIGHT = 0.30
MAX_GROSS = 0.60

LIFECYCLE_SCORES = {
    "强势扩散": 100.0,
    "低位修复": 75.0,
    "方向未明": 50.0,
    "退潮观察": 25.0,
    "极端低位": 10.0,
    "明显退潮": 0.0,
}


@dataclass(frozen=True, slots=True)
class CandidateInput:
    industry_code: str
    industry_name: str
    lifecycle_stage: str
    lifecycle_confidence: str
    etf_code: str | None
    etf_name: str | None
    mapping_tier: str
    mapping_eligible: bool
    mapping_active: bool
    decision_cutoff: date
    prices: tuple[PriceCandle, ...]
    industry_closes: tuple[tuple[date, float], ...]
    latest_fund_share: float | None
    master_listed: bool


def evaluate_candidate(value: CandidateInput) -> EtfRotationCandidate:
    prices = tuple(sorted(value.prices, key=lambda item: item.trade_date))
    latest = prices[-1] if prices else None
    amount20 = (
        median(item.amount_cny for item in prices[-20:] if item.amount_cny is not None)
        if any(item.amount_cny is not None for item in prices[-20:])
        else None
    )
    size = (
        latest.close * value.latest_fund_share
        if latest is not None and value.latest_fund_share is not None
        else None
    )
    return20 = _return(prices, 20)
    return60 = _return(prices, 60)
    lifecycle = LIFECYCLE_SCORES.get(value.lifecycle_stage, 0.0)
    relative = _relative_strength(prices, value.industry_closes)
    structure = _price_structure(prices)
    liquidity = _liquidity(amount20)
    overall = 0.35 * lifecycle + 0.30 * relative + 0.20 * structure + 0.15 * liquidity
    spread = _corwin_schultz_bps(prices[-21:])
    tracking = _tracking_error(prices, value.industry_closes)
    reasons: list[str] = []
    state: CandidateState = "eligible"
    if not value.mapping_active:
        state, reasons = "unavailable", ["mapping_not_effective_at_as_of"]
    elif value.etf_code is None or value.mapping_tier == "unavailable":
        state, reasons = "unavailable", ["mapping_unavailable"]
    elif value.mapping_tier != "exact" or not value.mapping_eligible:
        state, reasons = "context_only", [f"mapping_tier:{value.mapping_tier}"]
    elif latest is None or latest.trade_date < value.decision_cutoff:
        state, reasons = "stale", ["latest_bar_before_decision_cutoff"]
    else:
        if not value.master_listed:
            reasons.append("listed_master_unavailable")
        if len(prices) < MIN_SESSIONS:
            reasons.append("completed_sessions_below_252")
        if amount20 is None or amount20 < MIN_AMOUNT_CNY:
            reasons.append("median_amount_20d_below_20m")
        if size is None or size < MIN_SIZE_CNY:
            reasons.append("latest_size_below_100m")
        if spread is None:
            reasons.append("spread_proxy_unavailable")
        elif spread > SPREAD_PROXY_THRESHOLD_BPS:
            reasons.append("spread_proxy_above_35bp")
        if tracking is None:
            reasons.append("tracking_proxy_unavailable")
        elif tracking > TRACKING_PROXY_THRESHOLD:
            reasons.append("tracking_proxy_above_12pct")
        if structure < MIN_SCORE:
            reasons.append("price_structure_below_60")
        if overall < MIN_SCORE:
            reasons.append("overall_score_below_60")
        if reasons:
            state = "rejected"
    return EtfRotationCandidate(
        industry_code=value.industry_code,
        industry_name=value.industry_name,
        lifecycle_stage=value.lifecycle_stage,
        lifecycle_confidence=value.lifecycle_confidence,
        etf_code=value.etf_code,
        etf_name=value.etf_name,
        mapping_tier=value.mapping_tier,
        state=state,
        overall_score=round(overall, 2),
        lifecycle_score=lifecycle,
        relative_strength_score=round(relative, 2),
        price_structure_score=structure,
        liquidity_score=round(liquidity, 2),
        return_20d=return20,
        return_60d=return60,
        median_amount_20d_cny=amount20,
        latest_size_cny=size,
        spread_proxy_bps=spread,
        spread_evidence_kind=("corwin_schultz_ohlc_proxy" if spread is not None else "unavailable"),
        tracking_error_60d=tracking,
        tracking_evidence_kind=("sw_l1_exposure_proxy" if tracking is not None else "unavailable"),
        price_conclusion=_price_conclusion(structure, return20),
        rejection_reasons=tuple(reasons),
        candles=prices[-520:],
        weekly_candles=_aggregate(prices, "week"),
        monthly_candles=_aggregate(prices, "month"),
    )


def build_target_draft(
    candidates: tuple[EtfRotationCandidate, ...],
) -> EtfTargetDraft:
    ranked = sorted(
        (item for item in candidates if item.state == "eligible" and item.etf_code),
        key=lambda item: (-(item.overall_score or 0), item.etf_code or ""),
    )
    eligible = []
    seen: set[str] = set()
    for item in ranked:
        code = item.etf_code or ""
        if code in seen:
            continue
        seen.add(code)
        eligible.append(item)
        if len(eligible) == MAX_POSITIONS:
            break
    weights = tuple(
        EtfTargetWeight(
            industry_code=item.industry_code,
            etf_code=item.etf_code or "",
            target_weight=MAX_WEIGHT,
            reason=f"综合分 {item.overall_score:.2f}，代理门禁通过",
        )
        for item in eligible
    )
    gross = sum(item.target_weight for item in weights)
    return EtfTargetDraft(
        status="draft" if weights else "cash_only",
        weights=weights,
        cash_weight=round(1.0 - gross, 8),
        max_gross_weight=MAX_GROSS,
        known_gaps=(
            "current_holdings_not_connected",
            "research_target_not_portfolio_target",
        ),
    )


def blocked_replay(
    *,
    start_date: date | None,
    end_date: date | None,
    mapping_effective_from: date,
) -> EtfReplaySummary:
    return EtfReplaySummary(
        status="candidate_frozen",
        evidence_label="候选冻结历史回放不可用于晋级",
        start_date=start_date,
        end_date=end_date,
        known_gaps=(
            f"mapping_registered_from:{mapping_effective_from.isoformat()}",
            "point_in_time_lifecycle_history_not_published",
            "observed_bid_ask_history_not_published",
            "official_tracking_benchmark_history_not_published",
            "performance_metrics_withheld",
        ),
    )


def _return(prices: tuple[PriceCandle, ...], window: int) -> float | None:
    if len(prices) <= window or prices[-window - 1].close <= 0:
        return None
    return prices[-1].close / prices[-window - 1].close - 1.0


def _relative_strength(
    prices: tuple[PriceCandle, ...],
    industry_closes: tuple[tuple[date, float], ...],
) -> float:
    etf = {item.trade_date: item.close for item in prices}
    industry = dict(industry_closes)
    common = sorted(etf.keys() & industry.keys())
    if len(common) <= 60:
        return 0.0
    excess20 = _series_return(etf, common, 20) - _series_return(industry, common, 20)
    excess60 = _series_return(etf, common, 60) - _series_return(industry, common, 60)
    return _clamp(50.0 + 250.0 * (0.6 * excess20 + 0.4 * excess60))


def _price_structure(prices: tuple[PriceCandle, ...]) -> float:
    if len(prices) < 60:
        return 0.0
    close = prices[-1].close
    ma20 = sum(item.close for item in prices[-20:]) / 20
    ma60 = sum(item.close for item in prices[-60:]) / 60
    return (
        (30.0 if (_return(prices, 20) or 0) > 0 else 0.0)
        + (40.0 if close > ma20 else 0.0)
        + (30.0 if ma20 > ma60 else 0.0)
    )


def _liquidity(amount: float | None) -> float:
    if amount is None or amount <= MIN_AMOUNT_CNY:
        return 0.0
    return _clamp(
        100.0 * math.log(amount / MIN_AMOUNT_CNY) / math.log(200_000_000.0 / MIN_AMOUNT_CNY)
    )


def _tracking_error(
    prices: tuple[PriceCandle, ...],
    industry_closes: tuple[tuple[date, float], ...],
) -> float | None:
    etf = {item.trade_date: item.close for item in prices}
    industry = dict(industry_closes)
    common = sorted(etf.keys() & industry.keys())[-61:]
    if len(common) < 61:
        return None
    differences = [
        etf[today] / etf[yesterday] - industry[today] / industry[yesterday]
        for yesterday, today in pairwise(common)
        if etf[yesterday] > 0 and industry[yesterday] > 0
    ]
    return pstdev(differences) * math.sqrt(252) if len(differences) == 60 else None


def _corwin_schultz_bps(prices: tuple[PriceCandle, ...]) -> float | None:
    if len(prices) < 3:
        return None
    estimates = []
    denominator = 3.0 - 2.0 * math.sqrt(2.0)
    for previous, current in pairwise(prices):
        if min(previous.low, current.low) <= 0:
            continue
        beta = (
            math.log(previous.high / previous.low) ** 2 + math.log(current.high / current.low) ** 2
        )
        gamma = math.log(max(previous.high, current.high) / min(previous.low, current.low)) ** 2
        alpha = (math.sqrt(2.0 * beta) - math.sqrt(beta)) / denominator - math.sqrt(
            gamma / denominator
        )
        alpha = max(0.0, alpha)
        estimates.append(20_000.0 * (math.exp(alpha) - 1.0) / (1.0 + math.exp(alpha)))
    return median(estimates) if estimates else None


def _series_return(values: dict[date, float], dates: list[date], window: int) -> float:
    return values[dates[-1]] / values[dates[-window - 1]] - 1.0


def _price_conclusion(structure: float, return20: float | None) -> str:
    if structure >= 100 and (return20 or 0) <= 0.15:
        return "趋势确认，未过热"
    if structure >= 60:
        return "结构改善，仍需观察"
    return "价格结构未确认"


def _aggregate(
    prices: tuple[PriceCandle, ...],
    period: str,
) -> tuple[PriceCandle, ...]:
    grouped: dict[tuple[int, int], list[PriceCandle]] = {}
    for item in prices:
        key = (
            (item.trade_date.isocalendar().year, item.trade_date.isocalendar().week)
            if period == "week"
            else (item.trade_date.year, item.trade_date.month)
        )
        grouped.setdefault(key, []).append(item)
    return tuple(_combined(values) for values in grouped.values())


def _combined(values: list[PriceCandle]) -> PriceCandle:
    first, last = values[0], values[-1]
    amounts = [item.amount_cny for item in values if item.amount_cny is not None]
    return PriceCandle(
        trade_date=last.trade_date,
        open=first.open,
        high=max(item.high for item in values),
        low=min(item.low for item in values),
        close=last.close,
        volume_lots=sum(item.volume_lots for item in values),
        amount_cny=sum(amounts) if amounts else None,
    )


def _clamp(value: float) -> float:
    return min(100.0, max(0.0, value))


__all__ = [
    "SPREAD_PROXY_THRESHOLD_BPS",
    "STRATEGY_VERSION",
    "TRACKING_PROXY_THRESHOLD",
    "CandidateInput",
    "blocked_replay",
    "build_target_draft",
    "evaluate_candidate",
]
