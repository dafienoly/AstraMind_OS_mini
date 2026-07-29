"""Supportive evidence checks for read-only market-model challengers."""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil
from typing import Literal

import numpy as np

from ..application.identity import research_hash
from .contracts import EvidenceWindow, ModelValidationSummary


@dataclass(frozen=True)
class SafetyGates:
    coverage_not_worse: bool
    risk_not_worse: bool
    turnover_not_worse: bool
    cost_not_worse: bool

    @property
    def passed(self) -> bool:
        return all(
            (
                self.coverage_not_worse,
                self.risk_not_worse,
                self.turnover_not_worse,
                self.cost_not_worse,
            )
        )

    def reasons(self) -> tuple[str, ...]:
        return tuple(
            name
            for name, passed in (
                ("coverage_worse_than_incumbent", self.coverage_not_worse),
                ("risk_worse_than_incumbent", self.risk_not_worse),
                ("turnover_worse_than_incumbent", self.turnover_not_worse),
                ("cost_worse_than_incumbent", self.cost_not_worse),
            )
            if not passed
        )


@dataclass(frozen=True)
class BootstrapEstimate:
    mean: float
    lower_bound: float


@dataclass(frozen=True)
class LifecycleEvidence:
    macro_f1: float
    reference_macro_f1: float
    brier: float
    reference_brier: float
    calibration_error: float
    reference_calibration_error: float
    stage_return_monotonicity: float
    reference_stage_return_monotonicity: float


@dataclass(frozen=True)
class EtfEvidence:
    weekly_net_advantage: tuple[float, ...]
    cagr: float
    reference_cagr: float
    max_drawdown: float
    reference_max_drawdown: float
    calmar: float
    reference_calmar: float
    turnover: float
    reference_turnover: float
    tracking_error: float
    reference_tracking_error: float
    cost: float
    reference_cost: float


def block_bootstrap_mean(
    values: tuple[float, ...],
    *,
    block_size: int,
    confidence: float = 0.90,
    iterations: int = 2_000,
    seed: int = 20260729,
) -> BootstrapEstimate:
    if len(values) < block_size:
        raise ValueError("supportive bootstrap requires at least one complete block")
    if not 0 < confidence < 1 or iterations < 100 or block_size < 1:
        raise ValueError("invalid bootstrap configuration")
    array = np.asarray(values, dtype=float)
    if not np.isfinite(array).all():
        raise ValueError("bootstrap values must be finite")
    rng = np.random.default_rng(seed)
    block_count = ceil(len(array) / block_size)
    estimates = np.empty(iterations, dtype=float)
    offsets = np.arange(block_size)
    for iteration in range(iterations):
        starts = rng.integers(0, len(array), size=block_count)
        indexes = (starts[:, None] + offsets[None, :]).ravel()[: len(array)] % len(array)
        estimates[iteration] = float(np.mean(array[indexes]))
    return BootstrapEstimate(
        mean=float(np.mean(array)),
        lower_bound=float(np.quantile(estimates, 1.0 - confidence)),
    )


def validate_rank_series(
    *,
    manifest_id: str,
    window: EvidenceWindow,
    candidate_values: tuple[float, ...],
    reference_values: tuple[float, ...],
    safety: SafetyGates,
    metric_name: str = "daily_cross_section_rank_ic",
) -> ModelValidationSummary:
    if len(candidate_values) != len(reference_values):
        raise ValueError("candidate and reference evidence lengths must match")
    candidate = block_bootstrap_mean(candidate_values, block_size=20)
    reference = float(np.mean(reference_values))
    subperiods = tuple(float(np.mean(part)) for part in np.array_split(candidate_values, 3))
    supporting = sum(value > 0 for value in subperiods)
    reasons = list(safety.reasons())
    if candidate.mean < reference:
        reasons.append("validation_score_below_incumbent")
    if candidate.lower_bound <= 0:
        reasons.append("bootstrap_lower_bound_not_positive")
    if supporting < 2:
        reasons.append("fewer_than_two_supporting_subperiods")
    return _summary(
        manifest_id=manifest_id,
        window=window,
        metric_name=metric_name,
        candidate_value=candidate.mean,
        reference_value=reference,
        bootstrap_lower_bound=candidate.lower_bound,
        supporting=supporting,
        total=3,
        safety=safety,
        reasons=tuple(reasons),
    )


def validate_lifecycle(
    *,
    manifest_id: str,
    window: EvidenceWindow,
    evidence: LifecycleEvidence,
    safety: SafetyGates,
) -> tuple[ModelValidationSummary, ...]:
    definitions: tuple[tuple[str, float, float, Literal["higher", "lower"]], ...] = (
        ("macro_f1", evidence.macro_f1, evidence.reference_macro_f1, "higher"),
        ("brier", evidence.brier, evidence.reference_brier, "lower"),
        (
            "calibration_error",
            evidence.calibration_error,
            evidence.reference_calibration_error,
            "lower",
        ),
        (
            "stage_return_monotonicity",
            evidence.stage_return_monotonicity,
            evidence.reference_stage_return_monotonicity,
            "higher",
        ),
    )
    return tuple(
        _metric_comparison(
            manifest_id,
            window,
            name,
            candidate,
            reference,
            direction,
            safety,
        )
        for name, candidate, reference, direction in definitions
    )


def validate_etf(
    *,
    manifest_id: str,
    window: EvidenceWindow,
    evidence: EtfEvidence,
    safety: SafetyGates,
) -> tuple[ModelValidationSummary, ...]:
    bootstrap = block_bootstrap_mean(evidence.weekly_net_advantage, block_size=13)
    reasons = list(safety.reasons())
    if bootstrap.lower_bound <= 0:
        reasons.append("bootstrap_lower_bound_not_positive")
    advantage = _summary(
        manifest_id=manifest_id,
        window=window,
        metric_name="weekly_net_return_advantage",
        candidate_value=bootstrap.mean,
        reference_value=0.0,
        bootstrap_lower_bound=bootstrap.lower_bound,
        supporting=sum(value > 0 for value in evidence.weekly_net_advantage),
        total=len(evidence.weekly_net_advantage),
        safety=safety,
        reasons=tuple(reasons),
    )
    definitions: tuple[tuple[str, float, float, Literal["higher", "lower"]], ...] = (
        ("cagr", evidence.cagr, evidence.reference_cagr, "higher"),
        ("max_drawdown", evidence.max_drawdown, evidence.reference_max_drawdown, "lower"),
        ("calmar", evidence.calmar, evidence.reference_calmar, "higher"),
        ("turnover", evidence.turnover, evidence.reference_turnover, "lower"),
        (
            "tracking_error",
            evidence.tracking_error,
            evidence.reference_tracking_error,
            "lower",
        ),
        ("cost", evidence.cost, evidence.reference_cost, "lower"),
    )
    comparisons = tuple(
        _metric_comparison(
            manifest_id,
            window,
            name,
            candidate,
            reference,
            direction,
            safety,
        )
        for name, candidate, reference, direction in definitions
    )
    return (advantage, *comparisons)


def _metric_comparison(
    manifest_id: str,
    window: EvidenceWindow,
    name: str,
    candidate: float,
    reference: float,
    direction: Literal["higher", "lower"],
    safety: SafetyGates,
) -> ModelValidationSummary:
    supported = candidate >= reference if direction == "higher" else candidate <= reference
    reasons = [*safety.reasons()]
    if not supported:
        reasons.append(f"{name}_worse_than_incumbent")
    return _summary(
        manifest_id=manifest_id,
        window=window,
        metric_name=name,
        candidate_value=candidate,
        reference_value=reference,
        bootstrap_lower_bound=None,
        supporting=int(supported),
        total=1,
        safety=safety,
        reasons=tuple(reasons),
    )


def _summary(
    *,
    manifest_id: str,
    window: EvidenceWindow,
    metric_name: str,
    candidate_value: float,
    reference_value: float,
    bootstrap_lower_bound: float | None,
    supporting: int,
    total: int,
    safety: SafetyGates,
    reasons: tuple[str, ...],
) -> ModelValidationSummary:
    decision: Literal["pass", "fail"] = "pass" if not reasons and safety.passed else "fail"
    payload = {
        "manifest_id": manifest_id,
        "window": window,
        "metric_name": metric_name,
        "candidate_value": candidate_value,
        "reference_value": reference_value,
        "bootstrap_lower_bound": bootstrap_lower_bound,
        "subperiods_supporting": supporting,
        "subperiods_total": total,
        "safety": safety,
        "decision": decision,
        "reason_codes": reasons,
    }
    return ModelValidationSummary(
        validation_id="market-model-validation:" + research_hash(payload).removeprefix("sha256:"),
        manifest_id=manifest_id,
        window=window,
        metric_name=metric_name,
        candidate_value=candidate_value,
        reference_value=reference_value,
        bootstrap_lower_bound=bootstrap_lower_bound,
        subperiods_supporting=supporting,
        subperiods_total=total,
        coverage_not_worse=safety.coverage_not_worse,
        risk_not_worse=safety.risk_not_worse,
        turnover_not_worse=safety.turnover_not_worse,
        cost_not_worse=safety.cost_not_worse,
        decision=decision,
        reason_codes=reasons,
    )


__all__ = [
    "BootstrapEstimate",
    "EtfEvidence",
    "LifecycleEvidence",
    "SafetyGates",
    "block_bootstrap_mean",
    "validate_etf",
    "validate_lifecycle",
    "validate_rank_series",
]
