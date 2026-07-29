from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from astramind_mini.composition import create_app
from astramind_mini.config import Settings
from astramind_mini.market_regime.adapters import SnapshotIndustryResearchRanking
from astramind_mini.market_regime.contracts import (
    IndustryResearchRankingSnapshot,
    IndustryResearchRow,
    PriceCandle,
)


def test_ranking_api_serializes_same_snapshot_read_only_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot_id = "snapshot:sha256:" + "1" * 64
    candle = PriceCandle(
        trade_date=date(2026, 7, 28),
        open=10,
        high=11,
        low=9,
        close=10.5,
        volume_lots=100_000,
        amount_cny=10_000_000,
    )
    projection = IndustryResearchRankingSnapshot(
        status="ready",
        ranking_snapshot_id="ranking:sha256:" + "2" * 64,
        data_snapshot_id=snapshot_id,
        lifecycle_snapshot_id="lifecycle:sha256:" + "3" * 64,
        as_of=datetime(2026, 7, 29, 2, tzinfo=UTC),
        evidence_cutoff=date(2026, 7, 28),
        taxonomy="SW",
        taxonomy_version="SW2021",
        industry_code="801080.SI",
        industry_name="电子",
        lifecycle_stage="强势扩散",
        scoring_definition_version="industry-research-priority-v1.0.0",
        member_count=1,
        covered_member_count=1,
        content_hash="sha256:" + "4" * 64,
        rows=(
            IndustryResearchRow(
                instrument_id="000001.SZ",
                instrument_name="研究股份",
                membership_effective_as_of=date(2021, 1, 1),
                overall_priority=75,
                event_sentiment_score=70,
                technical_volume_score=80,
                fundamental_score=65,
                risk_score=30,
                reversal_repair_score=20,
                coverage=1,
                research_label="优先研究",
                evidence_cutoff=date(2026, 7, 28),
            ),
        ),
        selected_instrument_id="000001.SZ",
        candles=(candle,),
        weekly_candles=(candle,),
        monthly_candles=(candle,),
    )
    monkeypatch.setattr(
        SnapshotIndustryResearchRanking,
        "load",
        lambda self, **kwargs: projection,
    )

    response = TestClient(create_app(Settings(environment="test", data_dir=tmp_path))).get(
        "/api/market/industry-ranking",
        params={
            "data_snapshot_id": snapshot_id,
            "industry_code": "801080.SI",
            "instrument_id": "000001.SZ",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["data_snapshot_id"] == snapshot_id
    assert body["rows"][0]["research_label"] == "优先研究"
    assert body["candles"][0]["trade_date"] == body["evidence_cutoff"]
    assert all(
        forbidden not in response.text.lower()
        for forbidden in ("order_plan", "broker", "account_id", "paper", "live")
    )
