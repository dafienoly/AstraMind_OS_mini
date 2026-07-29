"""Deterministic helpers for the broker-free WP-0029 decision chain."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from datetime import date, datetime
from pathlib import Path
from typing import Any, cast

from astramind_mini.contracts import (
    FeatureSnapshot,
    OptimizationProblem,
    OptimizationResult,
    PortfolioTarget,
    PredictionBatch,
    StrategyVersion,
)
from astramind_mini.local_ops.contracts import DailyDecisionStatus
from astramind_mini.portfolio_risk.application.tactical_target import (
    build_tactical_target,
)
from astramind_mini.portfolio_risk.public import TacticalTargetDetails
from astramind_mini.strategy_research.adapters import DuckDBSealedReplaySource
from astramind_mini.strategy_research.application.identity import (
    build_feature_snapshot,
    build_prediction_batch,
    research_hash,
)
from astramind_mini.strategy_research.contracts import (
    EvidenceBundle,
    PromotionDecision,
    SealedReplayEvidence,
)
from astramind_mini.strategy_research.domain.sealed_models import (
    CurrentSignalCandidate,
)
from astramind_mini.trading_execution.contracts import ContinuousShadowOrderPlan

POLICY_VERSION = "wp-0029-daily-decision-v1.0.0"


def build_research_chain(
    source: DuckDBSealedReplaySource,
    snapshot_id: str,
    signal_date: date,
    decision_at: datetime,
    evidence: SealedReplayEvidence,
    strategy: StrategyVersion,
) -> tuple[
    tuple[CurrentSignalCandidate, ...],
    FeatureSnapshot,
    PredictionBatch,
    OptimizationProblem,
    OptimizationResult,
    PortfolioTarget,
    TacticalTargetDetails,
]:
    candidates = source.current_signals(
        family=evidence.family,
        horizon_sessions=evidence.horizon_sessions,
        signal_date=signal_date,
    )
    signals = tuple(item.signal for item in candidates)
    feature = build_feature_snapshot(
        data_snapshot_id=snapshot_id,
        as_of=decision_at,
        definition_version=strategy.feature_definition_version,
        signals=signals,
    )
    prediction = build_prediction_batch(
        strategy=strategy,
        feature_snapshot_id=feature.feature_snapshot_id,
        as_of=decision_at,
        horizon_sessions=evidence.horizon_sessions,
        signals=signals,
    )
    problem, result, target, details = build_tactical_target(
        prediction_batch_ids=(prediction.prediction_batch_id,),
        ranked_candidates=tuple(
            (item.signal.instrument_id, item.reference_price) for item in candidates
        ),
        as_of=decision_at,
    )
    return candidates, feature, prediction, problem, result, target, details


def build_artifact(
    commit: dict[str, object],
    promotion: PromotionDecision,
    evidence_id: str,
    strategy: StrategyVersion,
    feature: FeatureSnapshot,
    prediction: PredictionBatch,
    problem: OptimizationProblem,
    result: OptimizationResult,
    target: PortfolioTarget,
    details: TacticalTargetDetails,
    plan: ContinuousShadowOrderPlan,
    candidates: tuple[CurrentSignalCandidate, ...],
    next_open: date,
    guard: dict[str, object],
) -> dict[str, object]:
    return {
        "pipeline_commit": commit,
        "promotion_decision": promotion.model_dump(mode="json"),
        "evidence_id": evidence_id,
        "strategy_version": strategy.model_dump(mode="json"),
        "feature_snapshot": feature.model_dump(mode="json"),
        "prediction_batch": prediction.model_dump(mode="json"),
        "optimization_problem": problem.model_dump(mode="json"),
        "optimization_result": result.model_dump(mode="json"),
        "portfolio_target": target.model_dump(mode="json"),
        "target_details": asdict(details),
        "order_plan": plan.model_dump(mode="json"),
        "candidate_count": len(candidates),
        "candidates": [asdict(item) for item in candidates],
        "next_open_date": next_open,
        "paper_preflight": guard,
        "paper_dispatch_state": "disabled",
        "broker_connection_attempts": 0,
        "broker_write_attempts": 0,
        "broker_actions_allowed": False,
    }


def build_run_id(commit_id: str, promotion_id: str, state_id: str) -> str:
    digest = research_hash(
        {
            "pipeline_commit_id": commit_id,
            "promotion_decision_id": promotion_id,
            "shadow_state_id": state_id,
            "policy_version": POLICY_VERSION,
        }
    )
    return "daily-decision:" + digest.removeprefix("sha256:")


def build_preparation_run_id(commit_id: str, signal_date: date) -> str:
    digest = research_hash(
        {
            "pipeline_commit_id": commit_id,
            "signal_date": signal_date,
            "policy_version": POLICY_VERSION,
            "phase": "preparation",
        }
    )
    return "daily-decision:" + digest.removeprefix("sha256:")


def build_status(**values: object) -> DailyDecisionStatus:
    identity = {
        **values,
        "paper_dispatch_state": "disabled",
        "broker_connection_attempts": 0,
        "broker_write_attempts": 0,
        "broker_actions_allowed": False,
        "policy_version": POLICY_VERSION,
    }
    return DailyDecisionStatus.model_validate({**identity, "content_hash": research_hash(identity)})


def replace_status(value: DailyDecisionStatus, **changes: object) -> DailyDecisionStatus:
    identity = value.model_dump(exclude={"content_hash"})
    identity.update(changes)
    return DailyDecisionStatus.model_validate({**identity, "content_hash": research_hash(identity)})


def load_evidence_bundle(root: Path, bundle_id: str) -> EvidenceBundle:
    path = root / bundle_id.rsplit(":", 1)[-1] / "evidence-bundle.json"
    return EvidenceBundle.model_validate_json(path.read_text(encoding="utf-8"))


def paper_flags(database: Path) -> tuple[int, bool]:
    if not database.is_file():
        return 0, False
    with sqlite3.connect(database) as connection:
        baseline = _latest_payload(connection, "paper_account_baselines")
        projection = _latest_payload(connection, "paper_order_projections")
    open_orders = baseline.get("open_order_fingerprints", []) if baseline else []
    unknown = bool(projection and projection.get("state") == "submission_unknown")
    return len(open_orders) if isinstance(open_orders, list) else 0, unknown


def load_json(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def _latest_payload(connection: sqlite3.Connection, table: str) -> dict[str, Any] | None:
    exists = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    if not exists:
        return None
    row = connection.execute(
        f"SELECT payload_json FROM {table} ORDER BY rowid DESC LIMIT 1"
    ).fetchone()
    return cast(dict[str, Any], json.loads(str(row[0]))) if row else None


__all__ = [
    "POLICY_VERSION",
    "build_artifact",
    "build_preparation_run_id",
    "build_research_chain",
    "build_run_id",
    "build_status",
    "load_evidence_bundle",
    "load_json",
    "paper_flags",
    "replace_status",
]
