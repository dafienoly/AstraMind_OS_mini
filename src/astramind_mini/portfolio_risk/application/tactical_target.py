"""Construct a cash-valid tactical target from ranked candidates."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from datetime import UTC, datetime

from astramind_mini.contracts import (
    OptimizationProblem,
    OptimizationResult,
    PortfolioTarget,
    Sleeve,
)

from ..domain.tactical import TacticalTargetDetails, TargetHolding


def build_tactical_target(
    *,
    prediction_batch_ids: Sequence[str],
    ranked_candidates: Sequence[tuple[str, float]],
    as_of: datetime,
    capital_cny: float = 50_000,
) -> tuple[OptimizationProblem, OptimizationResult, PortfolioTarget, TacticalTargetDetails]:
    if as_of.tzinfo is None:
        raise ValueError("目标时点必须带时区")
    if capital_cny <= 0:
        raise ValueError("战术资金必须为正")
    unique: list[tuple[str, float]] = []
    seen: set[str] = set()
    for instrument_id, price in ranked_candidates:
        if instrument_id not in seen and price > 0:
            unique.append((instrument_id, price))
            seen.add(instrument_id)
        if len(unique) == 2:
            break
    weight = 0.5 if len(unique) == 2 else (0.9 if len(unique) == 1 else 0.0)
    holdings = tuple(TargetHolding(code, weight, price) for code, price in unique)
    payload = {
        "prediction_batch_ids": sorted(prediction_batch_ids),
        "holdings": [(item.instrument_id, item.weight, item.reference_price) for item in holdings],
        "capital_cny": capital_cny,
        "as_of": as_of.isoformat(),
    }
    digest = _hash(payload)
    problem = OptimizationProblem(
        optimization_problem_id=f"optimization-problem:{digest[7:]}",
        prediction_batch_ids=tuple(sorted(prediction_batch_ids)),
        portfolio_state_id="portfolio-state:cash-only-v1",
        constraints_version="tactical-50k-1-or-2-v1",
        cost_model_version="a-share-cost-v1",
        as_of=as_of,
        content_hash=digest,
    )
    created_at = as_of.astimezone(UTC)
    result_hash = _hash({"problem": problem.optimization_problem_id, "optimizer": "rank-v1"})
    result = OptimizationResult(
        optimization_result_id=f"optimization-result:{result_hash[7:]}",
        optimization_problem_id=problem.optimization_problem_id,
        optimizer_version="deterministic-rank-v1",
        created_at=created_at,
        content_hash=result_hash,
    )
    target_hash = _hash({"result": result.optimization_result_id, "payload": payload})
    target = PortfolioTarget(
        portfolio_target_id=f"portfolio-target:{target_hash[7:]}",
        optimization_result_id=result.optimization_result_id,
        sleeve=Sleeve.TACTICAL,
        as_of=as_of,
        content_hash=target_hash,
    )
    details = TacticalTargetDetails(
        target.portfolio_target_id,
        capital_cny,
        holdings,
        max(0.0, 1 - sum(item.weight for item in holdings)),
    )
    return problem, result, target, details


def _hash(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(payload.encode()).hexdigest()


__all__ = ["build_tactical_target"]
