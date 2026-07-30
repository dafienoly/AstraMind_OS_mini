"""Point-in-time construction of the U0-v1 research universe."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime
from statistics import median

from ..application.identity import research_hash
from .contracts import (
    CoreBoard,
    CoreDailyLiquidityObservation,
    CoreDiagnosticPool,
    CoreRiskObservation,
    CoreRiskStatus,
    CoreSecurityObservation,
    CoreUniverseDecision,
    CoreUniverseReason,
    CoreUniverseSpec,
)


def core_universe_content_hash(decisions: Sequence[CoreUniverseDecision]) -> str:
    """Hash the complete ordered U0 decision set, including diagnostic exclusions."""
    ordered = tuple(sorted(decisions, key=lambda item: item.instrument_id))
    if len({item.instrument_id for item in ordered}) != len(ordered):
        raise ValueError("a U0 decision set cannot contain duplicate instruments")
    return research_hash(ordered)


def evaluate_core_universe(
    *,
    security: CoreSecurityObservation,
    risk_history: Sequence[CoreRiskObservation],
    liquidity_history: Sequence[CoreDailyLiquidityObservation],
    common_sessions: Sequence[date],
    decision_date: date,
    cutoff_at: datetime,
    spec: CoreUniverseSpec | None = None,
) -> CoreUniverseDecision:
    """Evaluate research membership, new-risk eligibility and diagnostics separately."""
    rules = spec or CoreUniverseSpec()
    (
        research_member,
        reasons,
        pools,
        listed_sessions,
        sessions,
    ) = _membership_context(
        security=security,
        risk_history=risk_history,
        common_sessions=common_sessions,
        decision_date=decision_date,
        cutoff_at=cutoff_at,
        rules=rules,
    )
    amounts, observed_count = _liquidity_window(
        security.instrument_id,
        liquidity_history,
        sessions=tuple(day for day in sessions if day >= security.listed_on),
        cutoff_at=cutoff_at,
        window=rules.liquidity_window_common_sessions,
    )
    amount_median = (
        int(median(amounts))
        if len(amounts) == rules.liquidity_window_common_sessions
        else None
    )
    if research_member:
        _append_liquidity_reasons(
            security.instrument_id,
            liquidity_history,
            decision_date=decision_date,
            cutoff_at=cutoff_at,
            amount_median=amount_median,
            amount_count=len(amounts),
            rules=rules,
            reasons=reasons,
            pools=pools,
        )

    return CoreUniverseDecision(
        instrument_id=security.instrument_id,
        decision_date=decision_date,
        input_cutoff=cutoff_at,
        universe_version=rules.universe_version,
        research_member=research_member,
        new_risk_eligible=research_member and not reasons,
        diagnostic_pool=tuple(pools),
        reason_codes=tuple(reasons),
        listed_common_sessions=listed_sessions,
        liquidity_observation_count=observed_count,
        median_amount_20_cny=amount_median,
    )


def _membership_context(
    *,
    security: CoreSecurityObservation,
    risk_history: Sequence[CoreRiskObservation],
    common_sessions: Sequence[date],
    decision_date: date,
    cutoff_at: datetime,
    rules: CoreUniverseSpec,
) -> tuple[
    bool,
    list[CoreUniverseReason],
    list[CoreDiagnosticPool],
    int,
    tuple[date, ...],
]:
    visible_security = (
        security.available_at <= cutoff_at
        and security.listed_on <= decision_date
        and (security.delisted_on is None or security.delisted_on >= decision_date)
    )
    research_member = visible_security and security.board in rules.allowed_boards
    reasons: list[CoreUniverseReason] = []
    pools: list[CoreDiagnosticPool] = []

    if not visible_security:
        reasons.append(CoreUniverseReason.NOT_POINT_IN_TIME_LISTED)
    if security.board not in rules.allowed_boards:
        reasons.append(CoreUniverseReason.OUTSIDE_U0_BOARD)
        if security.board == CoreBoard.BSE:
            reasons.append(CoreUniverseReason.BSE_DIAGNOSTIC_ONLY)
            pools.append(CoreDiagnosticPool.BSE)

    sessions = tuple(sorted({day for day in common_sessions if day <= decision_date}))
    listed_sessions = sum(day >= security.listed_on for day in sessions)
    if research_member and listed_sessions < rules.minimum_listed_common_sessions:
        reasons.append(CoreUniverseReason.INSUFFICIENT_SEASONING)
        pools.append(CoreDiagnosticPool.NEW_STOCK)

    risk = _latest_visible_risk(
        security.instrument_id,
        risk_history,
        decision_date=decision_date,
        cutoff_at=cutoff_at,
    )
    if research_member:
        _append_risk_reasons(risk, reasons, pools)
    return research_member, reasons, pools, listed_sessions, sessions


def _append_liquidity_reasons(
    instrument_id: str,
    liquidity_history: Sequence[CoreDailyLiquidityObservation],
    *,
    decision_date: date,
    cutoff_at: datetime,
    amount_median: int | None,
    amount_count: int,
    rules: CoreUniverseSpec,
    reasons: list[CoreUniverseReason],
    pools: list[CoreDiagnosticPool],
) -> None:
    if amount_count < rules.liquidity_window_common_sessions:
        reasons.append(CoreUniverseReason.INSUFFICIENT_LIQUIDITY_HISTORY)
        _append_unique(pools, CoreDiagnosticPool.COVERAGE)
        return
    if amount_median is not None and amount_median < rules.minimum_median_amount_cny:
        reasons.append(CoreUniverseReason.MEDIAN_AMOUNT_BELOW_FLOOR)
        _append_unique(pools, CoreDiagnosticPool.COVERAGE)
    if not _latest_session_has_legal_bar(
        instrument_id,
        liquidity_history,
        decision_date=decision_date,
        cutoff_at=cutoff_at,
    ):
        reasons.append(CoreUniverseReason.CRITICAL_PRICE_UNAVAILABLE)
        _append_unique(pools, CoreDiagnosticPool.COVERAGE)


def _latest_visible_risk(
    instrument_id: str,
    history: Sequence[CoreRiskObservation],
    *,
    decision_date: date,
    cutoff_at: datetime,
) -> CoreRiskObservation | None:
    visible = [
        item
        for item in history
        if item.instrument_id == instrument_id
        and item.effective_on <= decision_date
        and item.available_at <= cutoff_at
    ]
    return (
        max(visible, key=lambda item: (item.effective_on, item.available_at))
        if visible
        else None
    )


def _append_risk_reasons(
    risk: CoreRiskObservation | None,
    reasons: list[CoreUniverseReason],
    pools: list[CoreDiagnosticPool],
) -> None:
    if risk is None or risk.status == CoreRiskStatus.UNKNOWN:
        reasons.append(CoreUniverseReason.RISK_STATUS_UNKNOWN)
        _append_unique(pools, CoreDiagnosticPool.RISK_STATE)
    elif risk.status in {CoreRiskStatus.ST, CoreRiskStatus.STAR_ST}:
        reasons.append(CoreUniverseReason.ST_OR_STAR_ST)
        _append_unique(pools, CoreDiagnosticPool.RISK_STATE)
    elif risk.status == CoreRiskStatus.DELISTING:
        reasons.append(CoreUniverseReason.DELISTING)
        _append_unique(pools, CoreDiagnosticPool.RISK_STATE)
    if risk is not None and risk.suspended:
        reasons.append(CoreUniverseReason.SUSPENDED)
        _append_unique(pools, CoreDiagnosticPool.SUSPENDED)


def _liquidity_window(
    instrument_id: str,
    history: Sequence[CoreDailyLiquidityObservation],
    *,
    sessions: tuple[date, ...],
    cutoff_at: datetime,
    window: int,
) -> tuple[list[int], int]:
    target_sessions = sessions[-window:]
    visible = {
        item.trade_date: item
        for item in history
        if item.instrument_id == instrument_id
        and item.trade_date in target_sessions
        and item.available_at <= cutoff_at
    }
    amounts = [
        int(item.amount_cny or 0) if (item := visible.get(day)) and item.has_legal_bar else 0
        for day in target_sessions
    ]
    return amounts, len(visible)


def _latest_session_has_legal_bar(
    instrument_id: str,
    history: Sequence[CoreDailyLiquidityObservation],
    *,
    decision_date: date,
    cutoff_at: datetime,
) -> bool:
    return any(
        item.instrument_id == instrument_id
        and item.trade_date == decision_date
        and item.available_at <= cutoff_at
        and item.has_legal_bar
        for item in history
    )


def _append_unique(values: list[CoreDiagnosticPool], value: CoreDiagnosticPool) -> None:
    if value not in values:
        values.append(value)


__all__ = ["core_universe_content_hash", "evaluate_core_universe"]
