"""Deterministic ETF model-data gates, including the prospective 60-day spread gate."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Sequence
from datetime import date, datetime
from statistics import median

from .contracts import (
    EtfModelDataGate,
    EtfNavObservation,
    EtfOfficialBenchmarkObservation,
    EtfSpreadMinuteObservation,
    GateStatus,
    OfficialIndexDailyObservation,
)

WINDOW_SESSIONS = 60
PLANNED_MINUTES = 240
QUALIFYING_SESSIONS = 54
MINUTE_COVERAGE = 0.90
MAX_MEDIAN_BPS = 15.0
MAX_P90_BPS = 35.0


def evaluate_etf_model_gate(
    *,
    instrument_id: str,
    evidence_cutoff: date,
    open_dates: Sequence[date],
    mappings: Iterable[EtfOfficialBenchmarkObservation],
    index_daily: Iterable[OfficialIndexDailyObservation],
    nav_rows: Iterable[EtfNavObservation],
    etf_trade_dates: Iterable[date],
    spread_rows: Iterable[EtfSpreadMinuteObservation],
    evaluated_at: datetime,
) -> EtfModelDataGate:
    sessions = tuple(sorted({day for day in open_dates if day <= evidence_cutoff}))[
        -WINDOW_SESSIONS:
    ]
    window_start = sessions[0] if sessions else None
    window_end = sessions[-1] if sessions else None
    reasons: list[str] = []
    mapping, mapping_status = _mapping_gate(
        instrument_id,
        window_start,
        mappings,
        reasons,
    )
    benchmark_status = _daily_coverage_gate(
        "official_benchmark",
        sessions,
        (
            row.trade_date
            for row in index_daily
            if mapping is not None and row.index_code == mapping.benchmark_code
        ),
        reasons,
    )
    nav_status = _nav_tradability_gate(
        instrument_id,
        sessions,
        nav_rows,
        etf_trade_dates,
        reasons,
    )
    spread_status, qualifying, coverage, spread_median, spread_p90 = _spread_gate(
        instrument_id,
        sessions,
        spread_rows,
        reasons,
    )
    statuses = (mapping_status, benchmark_status, nav_status, spread_status)
    return EtfModelDataGate(
        instrument_id=instrument_id,
        evidence_cutoff=evidence_cutoff,
        window_start=window_start,
        window_end=window_end,
        mapping_status=mapping_status,
        official_benchmark_status=benchmark_status,
        nav_tradability_status=nav_status,
        spread_status=spread_status,
        open_session_count=len(sessions),
        qualifying_spread_session_count=qualifying,
        planned_minutes_per_session=PLANNED_MINUTES,
        spread_minute_coverage_ratio=coverage,
        spread_median_bps=spread_median,
        spread_p90_bps=spread_p90,
        ready=all(status == "pass" for status in statuses),
        reason_codes=tuple(sorted(set(reasons))),
        evaluated_at=evaluated_at,
        schema_version="etf-model-data-gate-v1",
    )


def _mapping_gate(
    instrument_id: str,
    window_start: date | None,
    mappings: Iterable[EtfOfficialBenchmarkObservation],
    reasons: list[str],
) -> tuple[EtfOfficialBenchmarkObservation | None, GateStatus]:
    matches = tuple(row for row in mappings if row.instrument_id == instrument_id)
    if len(matches) != 1:
        reasons.append("official_benchmark_mapping_missing_or_ambiguous")
        return None, "fail"
    mapping = matches[0]
    if window_start is None or mapping.effective_from > window_start:
        reasons.append("official_benchmark_mapping_window_not_point_in_time")
        return mapping, "pending"
    return mapping, "pass"


def _daily_coverage_gate(
    name: str,
    sessions: tuple[date, ...],
    observed_dates: Iterable[date],
    reasons: list[str],
) -> GateStatus:
    if len(sessions) < WINDOW_SESSIONS:
        reasons.append(f"{name}_window_incomplete")
        return "pending"
    observed = set(observed_dates)
    covered = sum(day in observed for day in sessions)
    if covered < QUALIFYING_SESSIONS:
        reasons.append(f"{name}_coverage_below_90pct")
        return "fail"
    return "pass"


def _nav_tradability_gate(
    instrument_id: str,
    sessions: tuple[date, ...],
    nav_rows: Iterable[EtfNavObservation],
    etf_trade_dates: Iterable[date],
    reasons: list[str],
) -> GateStatus:
    if len(sessions) < WINDOW_SESSIONS:
        reasons.append("nav_tradability_window_incomplete")
        return "pending"
    nav_dates = {
        row.nav_date
        for row in nav_rows
        if row.instrument_id == instrument_id and row.announced_on <= sessions[-1]
    }
    trade_dates = set(etf_trade_dates)
    nav_covered = sum(day in nav_dates for day in sessions)
    tradable = sum(day in trade_dates for day in sessions)
    if nav_covered < QUALIFYING_SESSIONS:
        reasons.append("nav_coverage_below_90pct")
    if tradable < QUALIFYING_SESSIONS:
        reasons.append("tradability_coverage_below_90pct")
    enough_nav = nav_covered >= QUALIFYING_SESSIONS
    enough_tradability = tradable >= QUALIFYING_SESSIONS
    return "pass" if enough_nav and enough_tradability else "fail"


def _spread_gate(
    instrument_id: str,
    sessions: tuple[date, ...],
    spread_rows: Iterable[EtfSpreadMinuteObservation],
    reasons: list[str],
) -> tuple[GateStatus, int, float | None, float | None, float | None]:
    if not sessions:
        reasons.append("spread_window_incomplete")
        return "pending", 0, None, None, None
    session_set = set(sessions)
    rows = tuple(
        row
        for row in spread_rows
        if row.instrument_id == instrument_id
        and row.market_date in session_set
        and row.valid_quote_count > 0
    )
    counts = Counter((row.market_date, row.minute) for row in rows)
    unique_minutes_by_date = Counter(day for day, _ in counts)
    minimum_minutes = int(PLANNED_MINUTES * MINUTE_COVERAGE)
    qualified_dates = {
        day for day, count in unique_minutes_by_date.items() if count >= minimum_minutes
    }
    total_minutes = sum(unique_minutes_by_date.get(day, 0) for day in sessions)
    coverage = total_minutes / (len(sessions) * PLANNED_MINUTES)
    qualified_rows = tuple(row for row in rows if row.market_date in qualified_dates)
    medians = [
        row.quoted_spread_bps_median
        for row in qualified_rows
        if row.quoted_spread_bps_median is not None
    ]
    p90_values = [
        row.quoted_spread_bps_p90 for row in qualified_rows if row.quoted_spread_bps_p90 is not None
    ]
    spread_median = median(medians) if medians else None
    spread_p90 = _quantile(p90_values, 0.9) if p90_values else None
    if len(sessions) < WINDOW_SESSIONS:
        reasons.append("spread_window_incomplete")
        return "pending", len(qualified_dates), coverage, spread_median, spread_p90
    if len(qualified_dates) < QUALIFYING_SESSIONS:
        reasons.append("spread_session_coverage_below_90pct")
        return "pending", len(qualified_dates), coverage, spread_median, spread_p90
    failed = False
    if spread_median is None or spread_median > MAX_MEDIAN_BPS:
        reasons.append("spread_median_above_15bps")
        failed = True
    if spread_p90 is None or spread_p90 > MAX_P90_BPS:
        reasons.append("spread_p90_above_35bps")
        failed = True
    return (
        "fail" if failed else "pass",
        len(qualified_dates),
        coverage,
        spread_median,
        spread_p90,
    )


def _quantile(values: list[float], probability: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * probability
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


__all__ = ["evaluate_etf_model_gate"]
