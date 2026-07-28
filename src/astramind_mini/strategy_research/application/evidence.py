"""Deterministic sealed-replay evidence assembly."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import asdict
from datetime import date, datetime

from astramind_mini.contracts import StrategyVersion

from ..contracts import (
    EvidenceBundle,
    EvidenceMetrics,
    FailureEvidence,
    SealedReplayEvidence,
    YearEvidence,
)
from ..domain.backtest_models import BacktestResult, EquityPoint
from .identity import research_hash


def build_evidence_bundle(
    *,
    data_snapshot_id: str,
    frozen_candidate_set_id: str,
    development_cutoff: date,
    sealed_start: date,
    sealed_end: date,
    candidates: Mapping[tuple[str, int], StrategyVersion],
    results: Mapping[tuple[str, int], BacktestResult],
    created_at: datetime,
    limitations: Sequence[str] = (),
) -> EvidenceBundle:
    if development_cutoff >= sealed_start or sealed_start > sealed_end:
        raise ValueError("开发期与封存期边界无效")
    if set(candidates) != set(results):
        raise ValueError("冻结候选与封存结果集合不一致")
    evidence = tuple(
        _evidence(
            strategy=candidates[key],
            result=results[key],
            snapshot_id=data_snapshot_id,
            start=sealed_start,
            end=sealed_end,
            limitations=limitations,
        )
        for key in sorted(results)
    )
    identity = {
        "data_snapshot_id": data_snapshot_id,
        "frozen_candidate_set_id": frozen_candidate_set_id,
        "development_cutoff": development_cutoff,
        "sealed_start": sealed_start,
        "sealed_end": sealed_end,
        "evidence": [item.model_dump(mode="json") for item in evidence],
    }
    return EvidenceBundle(
        bundle_id="evidence-bundle:" + research_hash(identity),
        purpose="sealed_replay",
        data_snapshot_id=data_snapshot_id,
        frozen_candidate_set_id=frozen_candidate_set_id,
        development_cutoff=development_cutoff,
        sealed_start=sealed_start,
        sealed_end=sealed_end,
        evidence=evidence,
        created_at=created_at,
        broker_enabled=False,
    )


def _evidence(
    *,
    strategy: StrategyVersion,
    result: BacktestResult,
    snapshot_id: str,
    start: date,
    end: date,
    limitations: Sequence[str],
) -> SealedReplayEvidence:
    if not result.equity_curve:
        raise ValueError("封存结果缺少权益曲线")
    dates = [point.trade_date for point in result.equity_curve]
    if min(dates) < start or max(dates) > end:
        raise ValueError("封存结果包含评价窗口外数据")
    if strategy.execution_assumption_version != result.assumptions.version:
        raise ValueError("策略与封存结果执行假设不一致")
    result_identity = {
        "strategy_version_id": strategy.strategy_version_id,
        "family": result.strategy_family,
        "horizon_sessions": result.horizon_sessions,
        "events": result.events,
        "trades": result.trades,
        "equity_curve": result.equity_curve,
        "metrics": result.metrics,
    }
    result_hash = research_hash(result_identity)
    identity = {
        "result_hash": result_hash,
        "data_snapshot_id": snapshot_id,
        "window": (start, end),
    }
    metrics = EvidenceMetrics.model_validate(asdict(result.metrics))
    return SealedReplayEvidence(
        evidence_id="sealed-evidence:" + research_hash(identity),
        strategy_version_id=strategy.strategy_version_id,
        family=result.strategy_family,
        horizon_sessions=result.horizon_sessions,
        data_snapshot_id=snapshot_id,
        window_start=start,
        window_end=end,
        universe_version=strategy.universe_version,
        execution_assumption_version=result.assumptions.version,
        metrics=metrics,
        yearly=_yearly(result),
        failures=_failures(result),
        limitations=tuple(sorted(set(limitations))),
        result_hash=result_hash,
    )


def _yearly(result: BacktestResult) -> tuple[YearEvidence, ...]:
    points: dict[int, list[EquityPoint]] = {}
    for point in result.equity_curve:
        points.setdefault(point.trade_date.year, []).append(point)
    trade_counts = Counter(trade.exit_date.year for trade in result.trades)
    rows = []
    previous_end = result.assumptions.initial_cash_cny
    for year, values in sorted(points.items()):
        last = values[-1]
        start_equity = previous_end
        end_equity = last.equity_cny
        rows.append(
            YearEvidence(
                year=year,
                start_equity_cny=start_equity,
                end_equity_cny=end_equity,
                return_rate=end_equity / start_equity - 1,
                closed_trades=trade_counts[year],
            )
        )
        previous_end = end_equity
    return tuple(rows)


def _failures(result: BacktestResult) -> tuple[FailureEvidence, ...]:
    counts = Counter(
        event.reason for event in result.events if event.event_type.startswith("rejected")
    )
    return tuple(
        FailureEvidence(reason=reason, count=count) for reason, count in sorted(counts.items())
    )


__all__ = ["build_evidence_bundle"]
