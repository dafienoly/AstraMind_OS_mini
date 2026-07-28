"""Focused proof for sealed evidence and explicit manual promotion."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from astramind_mini.strategy_research.adapters import SQLitePromotionDecisionStore
from astramind_mini.strategy_research.application.backtest import DailyBacktestEngine
from astramind_mini.strategy_research.application.evidence import build_evidence_bundle
from astramind_mini.strategy_research.application.identity import freeze_strategy_version
from astramind_mini.strategy_research.application.promotion import ManualPromotionService
from astramind_mini.strategy_research.application.sealed_replay import SealedReplayRunner
from astramind_mini.strategy_research.contracts import EvidenceBundle
from astramind_mini.strategy_research.domain.backtest_models import CandidateSignal, ResearchBar
from astramind_mini.strategy_research.domain.sealed_models import ReplayCandidate, ReplayPrice


def _bar(index: int) -> ResearchBar:
    value = 10 + index * 0.02
    return ResearchBar(
        instrument_id="SYNTHETIC.SZ",
        trade_date=date(2023, 1, 1) + timedelta(days=index),
        open=value,
        high=value * 1.01,
        low=value * 0.99,
        close=value,
        research_close_index=value,
        amount_cny=100_000_000,
        turnover_rate=1.0,
        listed_sessions=100 + index,
        risk_status="normal",
        buy_state="tradable",
        sell_state="tradable",
    )


def _signal(
    history: Sequence[ResearchBar],
    horizon: int,
) -> CandidateSignal | None:
    if len(history) != 21:
        return None
    return CandidateSignal(
        instrument_id=history[-1].instrument_id,
        signal_date=history[-1].trade_date,
        family="momentum_breakout",
        horizon_sessions=horizon,
        score=1.0,
        reasons=("frozen_fixture",),
    )


def test_evidence_identity_is_stable_and_promotion_has_no_broker_side_effect(
    tmp_path: Path,
) -> None:
    created_at = datetime(2026, 7, 27, tzinfo=UTC)
    strategy = freeze_strategy_version(
        family="momentum_breakout",
        universe_version="tactical-universe-v1",
        execution_assumption_version="a-share-daily-execution-v1",
        created_at=created_at,
    )
    result = DailyBacktestEngine().run(
        bars=tuple(_bar(index) for index in range(30)),
        strategy_family="momentum_breakout",
        horizon_sessions=2,
        signal_function=_signal,
    )
    first = build_evidence_bundle(
        data_snapshot_id="snapshot:fixture",
        frozen_candidate_set_id="candidate-set:fixture",
        development_cutoff=date(2022, 12, 31),
        sealed_start=date(2023, 1, 1),
        sealed_end=date(2025, 12, 31),
        candidates={("momentum_breakout", 2): strategy},
        results={("momentum_breakout", 2): result},
        created_at=created_at,
        limitations=("synthetic_fixture",),
    )
    repeated = build_evidence_bundle(
        data_snapshot_id="snapshot:fixture",
        frozen_candidate_set_id="candidate-set:fixture",
        development_cutoff=date(2022, 12, 31),
        sealed_start=date(2023, 1, 1),
        sealed_end=date(2025, 12, 31),
        candidates={("momentum_breakout", 2): strategy},
        results={("momentum_breakout", 2): result},
        created_at=datetime(2026, 7, 28, tzinfo=UTC),
        limitations=("synthetic_fixture",),
    )
    assert first.bundle_id == repeated.bundle_id
    assert first.evidence[0].metrics.sortino >= 0
    assert not first.broker_enabled

    store = SQLitePromotionDecisionStore(tmp_path / "promotions.db")
    store.migrate()
    evidence = first.evidence[0]
    decision = ManualPromotionService(store).decide(
        bundle=first,
        evidence_id=evidence.evidence_id,
        strategy_version_id=evidence.strategy_version_id,
        outcome="promoted",
        rationale="用户基于封存证据明确选择",
        decided_at=created_at,
    )
    assert not decision.broker_enabled
    assert store.journal_mode() == "wal"
    assert store.latest_promoted("tactical") == decision
    assert (
        SQLitePromotionDecisionStore(tmp_path / "promotions.db").get(decision.decision_id)
        == decision
    )


def test_promotion_rejects_unmatched_or_empty_decision(tmp_path: Path) -> None:
    store = SQLitePromotionDecisionStore(tmp_path / "promotions.db")
    store.migrate()
    service = ManualPromotionService(store)
    with pytest.raises(ValueError, match="理由"):
        service.decide(
            bundle=_empty_bundle(),
            evidence_id="missing",
            strategy_version_id="missing",
            outcome="promoted",
            rationale="",
            decided_at=datetime(2026, 7, 27, tzinfo=UTC),
        )


class _SealedFixture:
    dates = tuple(date(2023, 1, 2) + timedelta(days=index) for index in range(5))

    def trading_dates(self, *, start_date: date, end_date: date) -> tuple[date, ...]:
        return tuple(value for value in self.dates if start_date <= value <= end_date)

    def candidates(
        self,
        *,
        family: str,
        horizon_sessions: int,
        start_date: date,
        end_date: date,
    ) -> tuple[ReplayCandidate, ...]:
        signal = CandidateSignal(
            "SYNTHETIC.SZ",
            self.dates[0],
            family,
            horizon_sessions,
            2.0,
            ("exact_snapshot_fixture",),
        )
        return (
            ReplayCandidate(
                signal,
                self.dates[1],
                10.0,
                100_000_000,
                "tradable",
                self.dates[2],
                self.dates[3],
                11.0,
            ),
        )

    def prices(
        self,
        *,
        instruments: tuple[str, ...],
        start_date: date,
        end_date: date,
    ) -> tuple[ReplayPrice, ...]:
        return tuple(
            ReplayPrice("SYNTHETIC.SZ", trade_date, 10.0 + index * 0.2)
            for index, trade_date in enumerate(self.dates)
            if start_date <= trade_date <= end_date
        )


def test_full_universe_replay_uses_next_open_and_defers_blocked_exit() -> None:
    result = SealedReplayRunner(_SealedFixture()).run(
        family="momentum_breakout",
        horizon_sessions=2,
        start_date=date(2023, 1, 2),
        end_date=date(2023, 1, 6),
    )
    assert result.trades[0].entry_date == date(2023, 1, 3)
    assert result.trades[0].exit_date == date(2023, 1, 5)
    assert any(event.reason == "sell_not_tradable_deferred" for event in result.events)
    assert result.metrics.closed_trades == 1


def _empty_bundle() -> EvidenceBundle:
    return EvidenceBundle(
        bundle_id="bundle:empty",
        purpose="sealed_replay",
        data_snapshot_id="snapshot:empty",
        frozen_candidate_set_id="candidate-set:empty",
        development_cutoff=date(2022, 12, 31),
        sealed_start=date(2023, 1, 1),
        sealed_end=date(2025, 12, 31),
        evidence=(),
        created_at=datetime(2026, 7, 27, tzinfo=UTC),
        broker_enabled=False,
    )
