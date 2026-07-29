"""Point-in-time ETF data-foundation qualification."""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from statistics import median
from typing import Literal

from .contracts import (
    EtfDailyObservation,
    EtfFoundationQualification,
    EtfIndustryMappingObservation,
    EtfMasterObservation,
    EtfShareObservation,
)

MIN_SESSIONS = 252
MIN_MEDIAN_AMOUNT_20D_CNY = 20_000_000.0
MIN_SIZE_CNY = 100_000_000.0
QualificationState = Literal[
    "foundation_eligible",
    "context_only",
    "insufficient_history",
    "insufficient_liquidity",
    "insufficient_size",
    "stale",
    "unavailable",
]


def qualify_etfs(
    *,
    data_snapshot_id: str,
    cutoff: date,
    masters: tuple[EtfMasterObservation, ...],
    daily: tuple[EtfDailyObservation, ...],
    shares: tuple[EtfShareObservation, ...],
    mappings: tuple[EtfIndustryMappingObservation, ...],
) -> tuple[EtfFoundationQualification, ...]:
    master_by_code = {
        row.instrument_id: row for row in masters if row.available_at.date() <= cutoff
    }
    daily_by_code = _before(daily, cutoff)
    share_by_code = _before(shares, cutoff)
    return tuple(
        _qualify(
            data_snapshot_id=data_snapshot_id,
            cutoff=cutoff,
            mapping=mapping,
            master=master_by_code.get(mapping.etf_code or ""),
            daily=tuple(daily_by_code.get(mapping.etf_code or "", ())),
            shares=tuple(share_by_code.get(mapping.etf_code or "", ())),
        )
        for mapping in mappings
    )


def _qualify(
    *,
    data_snapshot_id: str,
    cutoff: date,
    mapping: EtfIndustryMappingObservation,
    master: EtfMasterObservation | None,
    daily: tuple[EtfDailyObservation, ...],
    shares: tuple[EtfShareObservation, ...],
) -> EtfFoundationQualification:
    if mapping.effective_from > cutoff or (
        mapping.effective_to is not None and cutoff >= mapping.effective_to
    ):
        return EtfFoundationQualification(
            data_snapshot_id=data_snapshot_id,
            evidence_cutoff=cutoff,
            mapping_version=mapping.mapping_version,
            industry_code=mapping.industry_code,
            industry_name=mapping.industry_name,
            etf_code=mapping.etf_code,
            state="unavailable",
            completed_session_count=0,
            known_gaps=("mapping_not_effective_at_cutoff",),
        )
    ordered = sorted(daily, key=lambda row: row.trade_date)
    latest = ordered[-1] if ordered else None
    latest_share = max(shares, key=lambda row: row.trade_date) if shares else None
    amount = median(row.amount_cny for row in ordered[-20:]) if ordered else None
    size = (
        latest.close * latest_share.fund_share
        if latest is not None and latest_share is not None
        else None
    )
    gaps = ["spread_not_measured", "tracking_error_not_measured", "tradability_not_measured"]
    state: QualificationState = "foundation_eligible"
    if mapping.etf_code is None or mapping.semantic_tier == "unavailable":
        state, gaps = "unavailable", ["mapping_unavailable"]
    elif mapping.semantic_tier != "exact" or not mapping.eligible_for_foundation:
        state, gaps = "context_only", [f"mapping_tier:{mapping.semantic_tier}", *gaps]
    elif master is None or master.list_status != "L":
        state, gaps = "unavailable", ["listed_master_unavailable"]
    elif latest is None or latest.trade_date < cutoff:
        state, gaps = "stale", ["latest_bar_before_cutoff", *gaps]
    elif len(ordered) < MIN_SESSIONS:
        state, gaps = "insufficient_history", ["completed_sessions_below_252", *gaps]
    elif amount is None or amount < MIN_MEDIAN_AMOUNT_20D_CNY:
        state, gaps = "insufficient_liquidity", ["median_amount_20d_below_20m", *gaps]
    elif size is None or size < MIN_SIZE_CNY:
        state, gaps = "insufficient_size", ["latest_size_below_100m", *gaps]
    return EtfFoundationQualification(
        data_snapshot_id=data_snapshot_id,
        evidence_cutoff=cutoff,
        mapping_version=mapping.mapping_version,
        industry_code=mapping.industry_code,
        industry_name=mapping.industry_name,
        etf_code=mapping.etf_code,
        state=state,
        completed_session_count=len(ordered),
        median_amount_20d_cny=amount,
        latest_size_cny=size,
        known_gaps=tuple(gaps),
    )


def _before[Observation: (EtfDailyObservation, EtfShareObservation)](
    rows: tuple[Observation, ...],
    cutoff: date,
) -> dict[str, list[Observation]]:
    grouped: dict[str, list[Observation]] = defaultdict(list)
    for row in rows:
        if row.trade_date <= cutoff and row.available_at.date() <= cutoff:
            grouped[row.instrument_id].append(row)
    return grouped


__all__ = [
    "MIN_MEDIAN_AMOUNT_20D_CNY",
    "MIN_SESSIONS",
    "MIN_SIZE_CNY",
    "qualify_etfs",
]
