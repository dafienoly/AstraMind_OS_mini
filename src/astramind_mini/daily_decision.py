"""Composition root for the broker-free WP-0029 daily decision chain."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, cast

from astramind_mini.contracts import (
    FeatureSnapshot,
    PortfolioTarget,
    PredictionBatch,
    StrategyVersion,
)
from astramind_mini.daily_decision_support import (
    POLICY_VERSION,
    build_artifact,
    build_preparation_run_id,
    build_research_chain,
    build_run_id,
    build_status,
    load_evidence_bundle,
    load_json,
    paper_flags,
    replace_status,
)
from astramind_mini.data.adapters import DailyPipelineStore
from astramind_mini.data.contracts import DailyPipelineCommit
from astramind_mini.local_ops.contracts import DailyDecisionStatus
from astramind_mini.local_ops.daily_decision_store import DailyDecisionStore
from astramind_mini.local_ops.guard_store import OfflineGuardStore
from astramind_mini.local_ops.offline_guard import (
    OfflineDailyGuard,
    OfflineGuardInputs,
)
from astramind_mini.strategy_research.adapters import (
    DuckDBSealedReplaySource,
    SQLitePromotionDecisionStore,
)
from astramind_mini.strategy_research.application.identity import (
    freeze_strategy_version,
    research_hash,
)
from astramind_mini.strategy_research.contracts import (
    PromotionDecision,
    SealedReplayEvidence,
)
from astramind_mini.trading_execution.adapters import ContinuousShadowStore
from astramind_mini.trading_execution.contracts import (
    ContinuousShadowOrderPlan,
)
from astramind_mini.trading_execution.contracts.continuous_shadow import (
    ContinuousShadowState,
)
from astramind_mini.trading_execution.domain.continuous_shadow import (
    assess_drawdown,
    build_continuous_shadow_order_plan,
)

STEPS = ("research", "portfolio", "order_plan", "preflight", "publish")


class DailyDecisionInterrupted(RuntimeError):
    """Synthetic interruption after a durable WP-0029 checkpoint."""


@dataclass(frozen=True, slots=True)
class DailyDecisionResult:
    status: DailyDecisionStatus
    artifact_path: Path | None


class DailyDecisionOrchestrator:
    def __init__(
        self,
        *,
        data_root: Path,
        data_control_db: Path,
        promotion_db: Path,
        evidence_root: Path,
        shadow_db: Path,
        local_ops_db: Path,
        artifact_root: Path,
        backup_root: Path | None = None,
        recovery_root: Path | None = None,
        authorization_root: Path | None = None,
    ) -> None:
        self._data_root = data_root
        self._data_control = DailyPipelineStore(data_control_db, data_root)
        self._promotion_db = promotion_db
        self._evidence_root = evidence_root
        self._shadow_db = shadow_db
        self._local_ops_db = local_ops_db
        self._store = DailyDecisionStore(local_ops_db, artifact_root)
        self._backup_root = backup_root
        self._recovery_root = recovery_root
        self._authorization_root = authorization_root

    def run(
        self,
        *,
        started_at: datetime,
        interrupt_after_step: str | None = None,
    ) -> DailyDecisionResult:
        if started_at.tzinfo is None:
            raise ValueError("决策链启动时间必须带时区")
        try:
            commit = self._data_control.current_commit()
        except FileNotFoundError:
            return self._preparation_failure(
                pipeline_commit_id="daily-pipeline-commit:unavailable",
                signal_date=started_at.date(),
                started_at=started_at,
                state="waiting_data",
                blocker_code="daily_pipeline_commit_missing",
                recovery_action="先完成 WP-0025 日度数据提交，再重跑决策链",
            )
        source = DuckDBSealedReplaySource(self._data_root, commit.data_snapshot_id)
        signal_date = source.latest_trading_date()
        if signal_date != commit.target_date:
            return self._preparation_failure(
                pipeline_commit_id=commit.commit_id,
                signal_date=signal_date,
                started_at=started_at,
                state="blocked",
                blocker_code="research_inputs_stale",
                recovery_action="先补齐与日度提交日期一致的股票研究输入",
            )
        try:
            promotion, evidence, strategy, decision_at = self._promoted_strategy(
                commit.data_snapshot_id
            )
            shadow_store = ContinuousShadowStore(self._shadow_db)
            state = shadow_store.latest_state()
            if state is None:
                raise ValueError("持续 Shadow 本地起点尚未初始化")
        except (FileNotFoundError, ValueError):
            return self._preparation_failure(
                pipeline_commit_id=commit.commit_id,
                signal_date=signal_date,
                started_at=started_at,
                state="blocked",
                blocker_code="decision_prerequisite_invalid",
                recovery_action="核对晋级证据、策略版本与本地 Shadow 起点后重跑",
            )
        run_id = build_run_id(commit.commit_id, promotion.decision_id, state.state_id)
        existing = self._store.status(run_id)
        if existing and existing.state == "current":
            return DailyDecisionResult(existing, self._store.current_artifact())
        status = build_status(
            run_id=run_id,
            pipeline_commit_id=commit.commit_id,
            signal_date=signal_date,
            state="running",
            current_step="research",
            started_at=existing.started_at if existing else started_at,
            updated_at=started_at,
        )
        self._store.publish_status(status)
        try:
            return self._execute(
                source,
                commit=commit,
                promotion=promotion,
                evidence=evidence,
                strategy=strategy,
                state=state,
                signal_date=signal_date,
                decision_at=decision_at,
                run_id=run_id,
                status=status,
                interrupt_after_step=interrupt_after_step,
            )
        except DailyDecisionInterrupted:
            recovery = replace_status(
                status,
                state="recovery_required",
                blocker_codes=("decision_chain_interrupted",),
                recovery_action="使用同一日度提交身份从最后检查点恢复",
                updated_at=started_at,
            )
            self._store.publish_status(recovery)
            raise
        except Exception:
            blocked = replace_status(
                status,
                state="blocked",
                blocker_codes=("daily_decision_failed",),
                recovery_action="修复脱敏阻断后以相同输入恢复",
                updated_at=started_at,
            )
            self._store.publish_status(blocked)
            raise

    def _execute(
        self,
        source: DuckDBSealedReplaySource,
        *,
        commit: DailyPipelineCommit,
        promotion: PromotionDecision,
        evidence: SealedReplayEvidence,
        strategy: StrategyVersion,
        state: ContinuousShadowState,
        signal_date: date,
        decision_at: datetime,
        run_id: str,
        status: DailyDecisionStatus,
        interrupt_after_step: str | None,
    ) -> DailyDecisionResult:
        candidates, feature, prediction, problem, result, target, details = build_research_chain(
            source,
            commit.data_snapshot_id,
            signal_date,
            decision_at,
            evidence,
            strategy,
        )
        self._checkpoint(run_id, "research", prediction.prediction_batch_id, decision_at)
        self._interrupt(interrupt_after_step, "research")
        self._checkpoint(run_id, "portfolio", target.portfolio_target_id, decision_at)
        self._interrupt(interrupt_after_step, "portfolio")
        next_open = source.next_open_date(after_date=signal_date)
        decision = assess_drawdown(state, created_at=decision_at)
        plan = build_continuous_shadow_order_plan(
            target,
            details,
            state,
            decision,
            created_at=decision_at,
            earliest_execution_date=next_open,
        )
        self._checkpoint(run_id, "order_plan", plan.order_plan.order_plan_id, decision_at)
        self._interrupt(interrupt_after_step, "order_plan")
        guard = self._run_preflight(
            signal_date=signal_date,
            decision_at=decision_at,
            feature=feature,
            prediction=prediction,
            target=target,
            plan=plan,
        )
        self._checkpoint(run_id, "preflight", guard.run_id, decision_at)
        self._interrupt(interrupt_after_step, "preflight")
        artifact = build_artifact(
            commit.model_dump(mode="json"),
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
            candidates,
            next_open,
            guard.model_dump(mode="json"),
        )
        path, artifact_hash = self._publish_artifact(run_id, artifact)
        self._checkpoint(run_id, "publish", artifact_hash, decision_at)
        self._interrupt(interrupt_after_step, "publish")
        blockers = tuple(sorted(set(guard.blocker_codes)))
        completed = replace_status(
            status,
            state="current",
            current_step=None,
            feature_snapshot_id=feature.feature_snapshot_id,
            prediction_batch_id=prediction.prediction_batch_id,
            portfolio_target_id=target.portfolio_target_id,
            order_plan_id=plan.order_plan.order_plan_id,
            shadow_preflight_state=plan.status,
            paper_preflight_state=("ready" if guard.state == "completed" else "blocked"),
            blocker_codes=blockers,
            recovery_action=(
                None if not blockers else "按首个离线预检阻断完成本地恢复；Paper 派发继续禁用"
            ),
            updated_at=decision_at,
            completed_at=decision_at,
        )
        self._store.publish_status(completed)
        return DailyDecisionResult(completed, path)

    def _preparation_failure(
        self,
        *,
        pipeline_commit_id: str,
        signal_date: date,
        started_at: datetime,
        state: str,
        blocker_code: str,
        recovery_action: str,
    ) -> DailyDecisionResult:
        status = build_status(
            run_id=build_preparation_run_id(pipeline_commit_id, signal_date),
            pipeline_commit_id=pipeline_commit_id,
            signal_date=signal_date,
            state=state,
            current_step=None,
            blocker_codes=(blocker_code,),
            recovery_action=recovery_action,
            started_at=started_at,
            updated_at=started_at,
        )
        self._store.publish_status(status)
        return DailyDecisionResult(status, None)

    def _publish_artifact(self, run_id: str, artifact: dict[str, object]) -> tuple[Path, str]:
        artifact_hash = research_hash(artifact)
        encoded = json.dumps(
            {**artifact, "artifact_hash": artifact_hash},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode()
        return self._store.publish_artifact(run_id, artifact_hash, encoded), artifact_hash

    def _promoted_strategy(
        self, snapshot_id: str
    ) -> tuple[PromotionDecision, SealedReplayEvidence, StrategyVersion, datetime]:
        snapshot_path = (
            self._data_root / "snapshots" / snapshot_id.rsplit(":", 1)[-1] / "manifest.json"
        )
        snapshot = cast(dict[str, object], json.loads(snapshot_path.read_text(encoding="utf-8")))
        decision_at = datetime.fromisoformat(str(snapshot["as_of"]).replace("Z", "+00:00"))
        promotions = SQLitePromotionDecisionStore(self._promotion_db)
        promotions.migrate()
        promotion = promotions.latest_promoted("tactical")
        if promotion is None:
            raise ValueError("不存在已晋级的战术策略决定")
        bundle = load_evidence_bundle(self._evidence_root, promotion.evidence_bundle_id)
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
        return promotion, evidence, strategy, decision_at

    def _run_preflight(
        self,
        *,
        signal_date: Any,
        decision_at: datetime,
        feature: FeatureSnapshot,
        prediction: PredictionBatch,
        target: PortfolioTarget,
        plan: ContinuousShadowOrderPlan,
    ) -> Any:
        backup_id, recovery_id = self._backup_recovery()
        mandate_id, mandate_active = self._mandate(decision_at)
        foreign_orders, submission_unknown = paper_flags(self._shadow_db)
        inputs = OfflineGuardInputs(
            backup_id=backup_id,
            recovery_report_id=recovery_id,
            data_snapshot_id=feature.data_snapshot_id,
            feature_snapshot_id=feature.feature_snapshot_id,
            prediction_batch_id=prediction.prediction_batch_id,
            portfolio_target_id=target.portfolio_target_id,
            order_plan_id=plan.order_plan.order_plan_id,
            mandate_preview_id=mandate_id,
            data_fresh=True,
            foreign_open_order_count=foreign_orders,
            mandate_active=mandate_active,
            submission_unknown=submission_unknown,
        )
        return OfflineDailyGuard(OfflineGuardStore(self._local_ops_db)).run(
            logical_date=signal_date,
            owner_id=f"wp-0029:{signal_date.isoformat()}",
            inputs=inputs,
            started_at=decision_at,
        )

    def _backup_recovery(self) -> tuple[str | None, str | None]:
        if self._backup_root is None or self._recovery_root is None:
            return None, None
        manifests = tuple(sorted(self._backup_root.glob("daily/*/*/manifest.json")))
        healthy = [
            load_json(path) for path in manifests if load_json(path).get("status") == "complete"
        ]
        if not healthy:
            return None, None
        backup_id = str(healthy[-1]["backup_id"])
        reports = tuple(sorted(self._recovery_root.glob("*/report.json")))
        matching = [
            load_json(path)
            for path in reports
            if load_json(path).get("backup_id") == backup_id
            and load_json(path).get("status") == "healthy"
        ]
        return backup_id, str(matching[-1]["report_id"]) if matching else None

    def _mandate(self, at: datetime) -> tuple[str | None, bool]:
        if self._authorization_root is None:
            return None, False
        matches = tuple(sorted(self._authorization_root.glob("*/authorization.json")))
        if not matches:
            return None, False
        value = load_json(matches[-1])
        mandate = cast(dict[str, object], value.get("standing_mandate", {}))
        effective_to = mandate.get("effective_to")
        active = bool(effective_to and datetime.fromisoformat(str(effective_to)) >= at)
        return str(value.get("authorization_id") or "") or None, active

    def _checkpoint(self, run_id: str, step: str, artifact: str, completed_at: datetime) -> None:
        self._store.checkpoint(
            run_id=run_id,
            step_id=step,
            artifact_identity=artifact,
            completed_at=completed_at.isoformat(),
        )

    @staticmethod
    def _interrupt(requested: str | None, step: str) -> None:
        if requested == step:
            raise DailyDecisionInterrupted(f"在 {step} 检查点后模拟中断")


__all__ = [
    "POLICY_VERSION",
    "STEPS",
    "DailyDecisionInterrupted",
    "DailyDecisionOrchestrator",
    "DailyDecisionResult",
]
