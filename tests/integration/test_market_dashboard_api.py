import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from astramind_mini.composition import create_app
from astramind_mini.config import Settings
from astramind_mini.contracts import DatasetRef, DataSnapshot
from astramind_mini.market_regime.adapters import SnapshotMarketDashboard
from astramind_mini.market_regime.contracts import (
    BroadIndexView,
    MarketBreadth,
    MarketDashboardProjection,
    MarketLiquidity,
    MarketRegimeEvidence,
    PriceCandle,
)


def test_dashboard_api_returns_blocked_when_snapshot_lacks_broad_indexes(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "data"
    snapshot = DataSnapshot(
        snapshot_id="snapshot:sha256:" + "1" * 64,
        as_of=datetime(2026, 7, 29, 2, tzinfo=UTC),
        datasets=(
            DatasetRef(
                dataset_name="security_master",
                dataset_version="sha256:" + "3" * 64,
                schema_version="1.0.0",
                content_hash="sha256:" + "4" * 64,
            ),
        ),
        created_at=datetime(2026, 7, 29, 2, tzinfo=UTC),
        code_identity="dashboard-blocked-fixture",
    )
    snapshot_dir = data_root / "snapshots" / ("1" * 64)
    snapshot_dir.mkdir(parents=True)
    (snapshot_dir / "manifest.json").write_text(snapshot.model_dump_json(), encoding="utf-8")
    current = data_root / "current"
    current.mkdir()
    (current / "data-snapshot.json").write_text(
        json.dumps({"snapshot_id": snapshot.snapshot_id}),
        encoding="utf-8",
    )

    response = TestClient(create_app(Settings(environment="test", data_dir=data_root))).get(
        "/api/market/dashboard"
    )

    assert response.status_code == 200
    assert response.json()["status"] == "blocked"
    assert "missing_dataset:broad_index_daily" in response.json()["known_gaps"]


def test_dashboard_api_serializes_read_only_same_snapshot_projection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    projection = _projection()
    monkeypatch.setattr(SnapshotMarketDashboard, "current", lambda self: projection)

    response = TestClient(create_app(Settings(environment="test", data_dir=tmp_path))).get(
        "/api/market/dashboard"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["data_snapshot_id"] == projection.data_snapshot_id
    assert body["indexes"][0]["candles"][0]["trade_date"] == "2026-07-28"
    assert body["breadth"]["advance_ratio"] == 0.6
    serialized = response.text.lower()
    assert all(
        forbidden not in serialized
        for forbidden in ("order_plan", "broker", "account_id", "paper", "live")
    )


def _projection() -> MarketDashboardProjection:
    candle = PriceCandle(
        trade_date=date(2026, 7, 28),
        open=4500,
        high=4550,
        low=4480,
        close=4530,
        volume_lots=100_000,
        amount_cny=300_000_000,
    )
    return MarketDashboardProjection(
        status="ready",
        data_snapshot_id="snapshot:sha256:" + "2" * 64,
        as_of=datetime(2026, 7, 29, 2, tzinfo=UTC),
        evidence_cutoff=date(2026, 7, 28),
        projection_version="market-dashboard-v1.0.0",
        selected_index_id="000300.SH",
        indexes=(
            BroadIndexView(
                instrument_id="000300.SH",
                instrument_name="沪深300",
                latest_trade_date=date(2026, 7, 28),
                latest_close=4530,
                change=40,
                percent_change=0.89,
                return_20d=0.04,
                drawdown_250d=-0.03,
                candles=(candle,),
            ),
        ),
        breadth=MarketBreadth(
            advancing=3000,
            declining=1900,
            unchanged=100,
            advance_ratio=0.6,
            new_high_250d=88,
            new_low_250d=12,
            upper_limit_locked=70,
            lower_limit_locked=3,
        ),
        liquidity=MarketLiquidity(
            amount_cny=1_300_000_000_000,
            amount_change_20d=0.12,
            amount_percentile_250d=0.82,
        ),
        regime=MarketRegimeEvidence(
            state="strong",
            label="价格与参与同步增强",
            confidence=0.77,
            definition_version="market-regime-breadth-price-v1.0.0",
        ),
    )
