from __future__ import annotations

import argparse
import asyncio
import json
import os
from dataclasses import asdict
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import cast
from zoneinfo import ZoneInfo

from astramind_mini.config import Settings
from astramind_mini.contracts import (
    FeatureSnapshot,
    OptimizationProblem,
    OptimizationResult,
    PortfolioTarget,
    PredictionBatch,
    StrategyVersion,
)
from astramind_mini.data.adapters import TushareHttpClient, load_tushare_probe_config
from astramind_mini.portfolio_risk.application.tactical_target import build_tactical_target
from astramind_mini.portfolio_risk.public import TacticalTargetDetails
from astramind_mini.strategy_research.adapters import (
    DuckDBSealedReplaySource,
    SQLitePromotionDecisionStore,
)
from astramind_mini.strategy_research.application.identity import (
    build_feature_snapshot,
    build_prediction_batch,
    freeze_strategy_version,
    research_hash,
)
from astramind_mini.strategy_research.contracts import (
    EvidenceBundle,
    PromotionDecision,
    SealedReplayEvidence,
)
from astramind_mini.strategy_research.domain.sealed_models import CurrentSignalCandidate
from astramind_mini.trading_execution.adapters import ContinuousShadowStore
from astramind_mini.trading_execution.application import ContinuousShadowService
from astramind_mini.trading_execution.contracts import (
    ContinuousShadowCycle,
    ContinuousShadowOrderPlan,
)

SHANGHAI = ZoneInfo("Asia/Shanghai")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot-id", required=True)
    parser.add_argument("--signal-date", required=True, type=date.fromisoformat)
    parser.add_argument("--provider-env-file", required=True, type=Path)
    parser.add_argument("--data-root", type=Path, default=Path("var/data"))
    parser.add_argument(
        "--promotion-db", type=Path, default=Path("var/research/promotions.sqlite3")
    )
    parser.add_argument("--evidence-root", type=Path, default=Path("var/research/sealed"))
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("var/research/continuous-shadow"),
    )
    return parser.parse_args()


async def run(args: argparse.Namespace) -> int:
    settings = Settings()
    snapshot = _snapshot_manifest(args.data_root, args.snapshot_id)
    decision_at = datetime.fromisoformat(str(snapshot["created_at"]).replace("Z", "+00:00"))
    source = DuckDBSealedReplaySource(args.data_root, args.snapshot_id)
    if source.latest_trading_date() != args.signal_date:
        raise ValueError("信号日必须等于不可变快照中的最新完成交易日")

    promotion, evidence, strategy = _promoted_strategy(args, decision_at)
    candidates, feature, prediction, problem, result, target, details = _research_chain(
        source,
        args.snapshot_id,
        args.signal_date,
        decision_at,
        evidence,
        strategy,
    )

    calendar = await _calendar(
        settings,
        args.provider_env_file,
        args.signal_date + timedelta(days=1),
        args.signal_date + timedelta(days=14),
    )
    nominal_date, scheduled_date = _execution_dates(args.signal_date, decision_at, calendar[0])
    shadow_store = ContinuousShadowStore(settings.shadow_db_path)
    state = shadow_store.latest_state()
    if state is None:
        raise ValueError("持续 Shadow 本地起点尚未初始化")
    service = ContinuousShadowService(shadow_store)
    plan = service.prepare_plan(
        target=target,
        details=details,
        state=state,
        created_at=decision_at,
        earliest_execution_date=scheduled_date,
    )
    cycle = service.start_cycle(
        promotion_decision_id=promotion.decision_id,
        data_snapshot_id=args.snapshot_id,
        feature_snapshot_id=feature.feature_snapshot_id,
        prediction_batch_id=prediction.prediction_batch_id,
        target=target,
        plan=plan,
        signal_date=args.signal_date,
        nominal_execution_date=nominal_date,
        scheduled_execution_date=scheduled_date,
        created_at=decision_at,
    )
    artifact = _artifact(
        promotion,
        evidence.evidence_id,
        strategy,
        feature,
        prediction,
        problem,
        result,
        target,
        details,
        plan,
        cycle,
        candidates,
        calendar,
    )
    artifact_hash = research_hash(
        {
            "cycle_id": cycle.cycle_id,
            "feature_snapshot_id": feature.feature_snapshot_id,
            "prediction_batch_id": prediction.prediction_batch_id,
            "portfolio_target_id": target.portfolio_target_id,
            "order_plan_id": plan.order_plan.order_plan_id,
        }
    )
    output = args.output_root / artifact_hash.removeprefix("sha256:") / "cycle.json"
    _write_once(output, json.dumps(artifact, ensure_ascii=False, sort_keys=True, default=str))
    _print_summary(args.snapshot_id, feature, prediction, target, plan, cycle, candidates, details)
    return 0


def _promoted_strategy(
    args: argparse.Namespace,
    decision_at: datetime,
) -> tuple[PromotionDecision, SealedReplayEvidence, StrategyVersion]:
    store = SQLitePromotionDecisionStore(args.promotion_db)
    store.migrate()
    promotion = store.latest_promoted("tactical")
    if promotion is None:
        raise ValueError("不存在已晋级的战术策略决定")
    bundle = _evidence_bundle(args.evidence_root, promotion.evidence_bundle_id)
    evidence = next(
        (item for item in bundle.evidence if item.evidence_id == promotion.evidence_id),
        None,
    )
    if evidence is None or evidence.strategy_version_id != promotion.strategy_version_id:
        raise ValueError("晋级决定与封存证据身份不一致")
    strategy = freeze_strategy_version(
        family=evidence.family,
        horizon_sessions=evidence.horizon_sessions,
        universe_version=evidence.universe_version,
        execution_assumption_version=evidence.execution_assumption_version,
        created_at=decision_at,
    )
    if strategy.strategy_version_id != promotion.strategy_version_id:
        raise ValueError("当前策略定义已偏离获准晋级的精确版本")
    return promotion, evidence, strategy


def _research_chain(
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


def _artifact(
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
    cycle: ContinuousShadowCycle,
    candidates: tuple[CurrentSignalCandidate, ...],
    calendar: tuple[tuple[date, ...], str],
) -> dict[str, object]:
    return {
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
        "cycle": cycle.model_dump(mode="json"),
        "candidate_count": len(candidates),
        "candidates": [asdict(item) for item in candidates],
        "calendar_evidence": {
            "open_dates": [item.isoformat() for item in calendar[0]],
            "source_endpoint": calendar[1],
        },
    }


def _print_summary(
    snapshot_id: str,
    feature: FeatureSnapshot,
    prediction: PredictionBatch,
    target: PortfolioTarget,
    plan: ContinuousShadowOrderPlan,
    cycle: ContinuousShadowCycle,
    candidates: tuple[CurrentSignalCandidate, ...],
    details: TacticalTargetDetails,
) -> None:
    print(f"data_snapshot_id={snapshot_id}")
    print(f"feature_snapshot_id={feature.feature_snapshot_id}")
    print(f"prediction_batch_id={prediction.prediction_batch_id}")
    print(f"portfolio_target_id={target.portfolio_target_id}")
    print(f"order_plan_id={plan.order_plan.order_plan_id}")
    print(f"continuous_shadow_cycle_id={cycle.cycle_id}")
    print(f"candidate_count={len(candidates)}")
    print(f"target_holding_count={len(details.holdings)}")
    print(f"status={cycle.status}")
    print(f"scheduled_execution_date={cycle.scheduled_execution_date.isoformat()}")
    print("broker_actions_allowed=false")


def _snapshot_manifest(root: Path, snapshot_id: str) -> dict[str, object]:
    path = root / "snapshots" / snapshot_id.rsplit(":", 1)[-1] / "manifest.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("snapshot_id") != snapshot_id:
        raise ValueError("数据快照身份与路径不一致")
    return cast(dict[str, object], payload)


def _evidence_bundle(root: Path, bundle_id: str) -> EvidenceBundle:
    path = root / bundle_id.rsplit(":", 1)[-1] / "evidence-bundle.json"
    return EvidenceBundle.model_validate_json(path.read_text(encoding="utf-8"))


async def _calendar(
    settings: Settings,
    provider_env_file: Path,
    start: date,
    end: date,
) -> tuple[tuple[date, ...], str]:
    client = TushareHttpClient(load_tushare_probe_config(settings, provider_env_file))
    table = await client.query(
        "trade_cal",
        params={
            "exchange": "SSE",
            "start_date": start.strftime("%Y%m%d"),
            "end_date": end.strftime("%Y%m%d"),
        },
        fields=("exchange", "cal_date", "is_open", "pretrade_date"),
    )
    opens = tuple(
        sorted(
            date.fromisoformat(str(row["cal_date"]))
            for row in table.rows
            if int(str(row["is_open"])) == 1
        )
    )
    if not opens:
        raise ValueError("未来交易日历没有可执行交易日")
    return opens, table.source_endpoint


def _execution_dates(
    signal_date: date,
    decision_at: datetime,
    open_dates: tuple[date, ...],
) -> tuple[date, date]:
    nominal = next(item for item in open_dates if item > signal_date)
    local = decision_at.astimezone(SHANGHAI)
    current_open_available = local.time() < time(9, 30)
    scheduled = next(
        item
        for item in open_dates
        if item > local.date() or (item == local.date() and current_open_available)
    )
    return nominal, scheduled


def _write_once(path: Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_text(encoding="utf-8") != payload:
            raise ValueError("持续 Shadow 周期制品身份发生内容冲突")
        return
    temporary = path.with_suffix(".tmp")
    temporary.write_text(payload, encoding="utf-8")
    os.replace(temporary, path)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run(parse_args())))
