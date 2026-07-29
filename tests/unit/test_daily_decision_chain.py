from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

import astramind_mini.daily_decision as module
from astramind_mini.data.adapters import DailyPipelineStore
from astramind_mini.data.application.identity import content_hash
from astramind_mini.data.contracts import DailyPipelineCommit
from astramind_mini.strategy_research.application.identity import freeze_strategy_version
from astramind_mini.strategy_research.contracts import (
    EvidenceBundle,
    EvidenceMetrics,
    PromotionDecision,
    SealedReplayEvidence,
)
from astramind_mini.strategy_research.domain.backtest_models import CandidateSignal
from astramind_mini.strategy_research.domain.sealed_models import CurrentSignalCandidate
from astramind_mini.trading_execution.contracts.continuous_shadow import (
    ContinuousShadowState,
)

NOW = datetime(2026, 7, 28, 10, tzinfo=UTC)
SNAPSHOT_ID = "snapshot:sha256:" + "1" * 64


class FakeSource:
    latest_date = date(2026, 7, 27)

    def __init__(self, data_root: Path, snapshot_id: str) -> None:
        assert snapshot_id == SNAPSHOT_ID

    def latest_trading_date(self) -> date:
        return self.latest_date

    def next_open_date(self, *, after_date: date) -> date:
        assert after_date == date(2026, 7, 27)
        return date(2026, 7, 28)

    def current_signals(
        self, *, family: str, horizon_sessions: int, signal_date: date
    ) -> tuple[CurrentSignalCandidate, ...]:
        return (
            CurrentSignalCandidate(
                signal=CandidateSignal(
                    instrument_id="000001.SZ",
                    signal_date=signal_date,
                    family=family,
                    horizon_sessions=horizon_sessions,
                    score=1.0,
                    reasons=("synthetic",),
                ),
                reference_price=10.0,
            ),
        )


class FakePromotionStore:
    decision: PromotionDecision

    def __init__(self, database: Path) -> None:
        pass

    def migrate(self) -> None:
        pass

    def latest_promoted(self, sleeve: str) -> PromotionDecision:
        assert sleeve == "tactical"
        return self.decision


class FakeShadowStore:
    state: ContinuousShadowState

    def __init__(self, database: Path) -> None:
        pass

    def latest_state(self) -> ContinuousShadowState:
        return self.state


def test_decision_chain_recovers_without_cycle_or_broker_action(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    orchestrator = _build_orchestrator(tmp_path, monkeypatch)
    with pytest.raises(module.DailyDecisionInterrupted):
        orchestrator.run(started_at=NOW, interrupt_after_step="research")
    interrupted = orchestrator._store.latest_status()
    assert interrupted is not None and interrupted.state == "recovery_required"
    assert not (tmp_path / "decision/current.json").exists()

    completed = orchestrator.run(started_at=NOW)
    assert completed.status.state == "current"
    assert completed.status.paper_dispatch_state == "disabled"
    assert completed.status.broker_actions_allowed is False
    assert completed.artifact_path is not None
    artifact = json.loads(completed.artifact_path.read_text(encoding="utf-8"))
    assert "cycle" not in artifact
    assert artifact["broker_connection_attempts"] == 0
    assert artifact["broker_write_attempts"] == 0
    repeated = orchestrator.run(started_at=NOW)
    assert repeated.status == completed.status
    assert repeated.artifact_path == completed.artifact_path
    assert content_hash(artifact) != ""


def test_decision_chain_exposes_stale_research_inputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    orchestrator = _build_orchestrator(tmp_path, monkeypatch)
    FakeSource.latest_date = date(2026, 7, 26)

    result = orchestrator.run(started_at=NOW)

    assert result.status.state == "blocked"
    assert result.status.blocker_codes == ("research_inputs_stale",)
    assert result.artifact_path is None


def test_decision_chain_exposes_promotion_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    orchestrator = _build_orchestrator(tmp_path, monkeypatch)
    FakePromotionStore.decision = FakePromotionStore.decision.model_copy(
        update={"strategy_version_id": "strategy-version:drifted"}
    )

    result = orchestrator.run(started_at=NOW)

    assert result.status.state == "blocked"
    assert result.status.blocker_codes == ("decision_prerequisite_invalid",)
    assert result.artifact_path is None


def test_decision_chain_waits_for_pipeline_commit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    orchestrator = _build_orchestrator(tmp_path, monkeypatch)

    def missing_commit(self: DailyPipelineStore) -> DailyPipelineCommit:
        raise FileNotFoundError

    monkeypatch.setattr(DailyPipelineStore, "current_commit", missing_commit)
    result = orchestrator.run(started_at=NOW)

    assert result.status.state == "waiting_data"
    assert result.status.blocker_codes == ("daily_pipeline_commit_missing",)
    assert result.artifact_path is None


def _build_orchestrator(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> module.DailyDecisionOrchestrator:
    FakeSource.latest_date = date(2026, 7, 27)
    strategy = freeze_strategy_version(
        family="reversal_volume_price",
        horizon_sessions=10,
        universe_version="synthetic-universe-v1",
        execution_assumption_version="synthetic-execution-v1",
        created_at=NOW,
    )
    evidence = SealedReplayEvidence(
        evidence_id="sealed-evidence:synthetic",
        strategy_version_id=strategy.strategy_version_id,
        family="reversal_volume_price",
        horizon_sessions=10,
        data_snapshot_id="snapshot:sealed",
        window_start=date(2023, 1, 1),
        window_end=date(2025, 12, 31),
        universe_version=strategy.universe_version,
        execution_assumption_version=strategy.execution_assumption_version,
        metrics=EvidenceMetrics(
            total_return=0,
            annualized_return=0,
            annualized_volatility=0,
            sharpe=0,
            sortino=0,
            max_drawdown=0,
            calmar=0,
            win_rate=0,
            payoff_ratio=0,
            turnover=0,
            closed_trades=0,
            rejected_orders=0,
        ),
        yearly=(),
        failures=(),
        limitations=("synthetic",),
        result_hash="sha256:" + "2" * 64,
    )
    bundle = EvidenceBundle(
        bundle_id="evidence-bundle:synthetic",
        purpose="sealed_replay",
        data_snapshot_id="snapshot:sealed",
        frozen_candidate_set_id="candidate-set:synthetic",
        development_cutoff=date(2022, 12, 31),
        sealed_start=date(2023, 1, 1),
        sealed_end=date(2025, 12, 31),
        evidence=(evidence,),
        created_at=NOW,
    )
    FakePromotionStore.decision = PromotionDecision(
        decision_id="promotion:synthetic",
        strategy_version_id=strategy.strategy_version_id,
        evidence_bundle_id=bundle.bundle_id,
        evidence_id=evidence.evidence_id,
        sleeve="tactical",
        outcome="promoted",
        rationale="synthetic",
        decided_at=NOW,
    )
    FakeShadowStore.state = ContinuousShadowState(
        state_id="continuous-shadow-state:synthetic",
        disposition_id="disposition:synthetic",
        trading_date=date(2026, 7, 27),
        as_of=NOW,
        cash_cny=50_000,
        positions=(),
        equity_cny=50_000,
        sleeve_peak_equity_cny=50_000,
        account_equity_cny=50_000,
        account_peak_equity_cny=50_000,
        content_hash="sha256:" + "3" * 64,
    )
    commit = DailyPipelineCommit(
        commit_id="daily-pipeline-commit:synthetic",
        run_id="daily-pipeline:synthetic",
        target_date=date(2026, 7, 27),
        data_snapshot_id=SNAPSHOT_ID,
        rotation_snapshot_id="rotation:synthetic",
        committed_at=NOW,
        content_hash="sha256:" + "4" * 64,
    )
    monkeypatch.setattr(module, "DuckDBSealedReplaySource", FakeSource)
    monkeypatch.setattr(module, "SQLitePromotionDecisionStore", FakePromotionStore)
    monkeypatch.setattr(module, "ContinuousShadowStore", FakeShadowStore)
    monkeypatch.setattr(
        DailyPipelineStore,
        "current_commit",
        lambda self: commit,
    )
    snapshot = tmp_path / "data/snapshots" / ("1" * 64) / "manifest.json"
    snapshot.parent.mkdir(parents=True)
    snapshot.write_text(
        json.dumps({"snapshot_id": SNAPSHOT_ID, "as_of": NOW.isoformat()}),
        encoding="utf-8",
    )
    evidence_path = (
        tmp_path / "sealed" / bundle.bundle_id.rsplit(":", 1)[-1] / "evidence-bundle.json"
    )
    evidence_path.parent.mkdir(parents=True)
    evidence_path.write_text(bundle.model_dump_json(), encoding="utf-8")
    orchestrator = module.DailyDecisionOrchestrator(
        data_root=tmp_path / "data",
        data_control_db=tmp_path / "data.sqlite3",
        promotion_db=tmp_path / "promotion.sqlite3",
        evidence_root=tmp_path / "sealed",
        shadow_db=tmp_path / "shadow.sqlite3",
        local_ops_db=tmp_path / "ops.sqlite3",
        artifact_root=tmp_path / "decision",
    )
    return orchestrator
