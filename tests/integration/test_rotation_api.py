import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from astramind_mini.composition import create_app
from astramind_mini.config import Settings
from astramind_mini.contracts import DatasetRef, DataSnapshot
from astramind_mini.market_regime.adapters.snapshot_hierarchy import (
    SnapshotIndustryHierarchy,
)
from astramind_mini.market_regime.contracts import (
    IndustryHierarchyView,
    PriceCandle,
    ShareholderConcentrationEvidence,
    StockEvidence,
    StockFundamentalEvidence,
)
from scripts.e2e_rotation_fixture import prepare


def test_rotation_api_fails_closed_when_no_snapshot(tmp_path: Path) -> None:
    client = TestClient(
        create_app(Settings(environment="test", rotation_data_dir=tmp_path / "rotation"))
    )
    response = client.get("/api/market/industry-rotation")
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "rotation_snapshot_not_available"


def test_rotation_api_returns_verified_read_only_snapshot(tmp_path: Path) -> None:
    rotation_dir = tmp_path / "rotation"
    expected = prepare(rotation_dir)
    client = TestClient(create_app(Settings(environment="test", rotation_data_dir=rotation_dir)))

    response = client.get("/api/market/industry-rotation")

    assert response.status_code == 200
    assert response.json()["rotation_snapshot_id"] == expected.rotation_snapshot_id
    serialized = response.text.lower()
    assert all(
        forbidden not in serialized
        for forbidden in ("broker", "account", "order_plan", "paper", "live")
    )


def test_hierarchy_api_reports_missing_l2_without_substitution(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    digest = "1" * 64
    manifest_dir = data_root / "datasets" / "trade_calendar" / digest
    manifest_dir.mkdir(parents=True)
    (manifest_dir / "manifest.json").write_text(
        json.dumps({"artifact_paths": []}), encoding="utf-8"
    )
    snapshot = DataSnapshot(
        snapshot_id="snapshot:sha256:" + "2" * 64,
        as_of=datetime(2026, 7, 28, 18, tzinfo=UTC),
        datasets=(
            DatasetRef(
                dataset_name="trade_calendar",
                dataset_version="sha256:" + digest,
                schema_version="1.0.0",
                content_hash="sha256:" + "3" * 64,
            ),
        ),
        created_at=datetime(2026, 7, 28, 18, tzinfo=UTC),
        code_identity="test-hierarchy",
    )
    snapshot_dir = data_root / "snapshots" / ("2" * 64)
    snapshot_dir.mkdir(parents=True)
    (snapshot_dir / "manifest.json").write_text(snapshot.model_dump_json(), encoding="utf-8")
    client = TestClient(create_app(Settings(environment="test", data_dir=data_root)))
    response = client.get(
        "/api/market/industry-hierarchy",
        params={
            "data_snapshot_id": snapshot.snapshot_id,
            "as_of": "2026-07-28",
            "parent_code": "801080.SI",
        },
    )
    assert response.status_code == 200
    assert response.json()["status"] == "blocked"
    assert response.json()["known_gaps"] == [
        "missing_datasets:daily_market,industry_index_daily,industry_membership,"
        "industry_taxonomy,security_master"
    ]


def test_hierarchy_api_serializes_periods_and_same_snapshot_stock_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candle = PriceCandle(
        trade_date=date(2026, 7, 27),
        open=10,
        high=11,
        low=9,
        close=10.5,
        volume_lots=1000,
        amount_cny=2_000_000,
    )
    fundamental = StockFundamentalEvidence(
        market_date=date(2026, 7, 27),
        available_at=datetime(2026, 7, 27, 18, tzinfo=UTC),
        latest_close=10.5,
        percent_change=0.02,
        turnover_rate=0.03,
        price_earnings_ttm=20,
        price_book=2,
        total_market_value_cny=1_000_000_000,
        circulating_market_value_cny=800_000_000,
        amount_cny=2_000_000,
    )
    shareholder = ShareholderConcentrationEvidence(
        status="ready",
        announced_on=date(2026, 7, 18),
        reporting_period=date(2026, 6, 30),
        available_at=datetime(2026, 7, 18, 18, tzinfo=UTC),
        holder_count=900,
        previous_holder_count=1000,
        change_rate=-0.1,
        direction="concentrating",
        consecutive_periods=1,
        observation_age_days=9,
    )
    evidence = StockEvidence(
        instrument_id="688981.SH",
        instrument_name="中芯国际",
        as_of=date(2026, 7, 27),
        fundamental=fundamental,
        fundamental_history=(fundamental,),
        shareholder_concentration=shareholder,
        shareholder_concentration_history=(shareholder,),
    )
    view = IndustryHierarchyView(
        status="ready",
        data_snapshot_id="snapshot:sha256:" + "4" * 64,
        as_of=date(2026, 7, 27),
        level="stock",
        comparison_scope="members",
        benchmark_id="SW2021:L2:801081.SI:member_equal_weight_return",
        selected_code="688981.SH",
        candles=(candle,),
        weekly_candles=(candle,),
        monthly_candles=(candle,),
        stock_evidence=evidence,
    )
    monkeypatch.setattr(SnapshotIndustryHierarchy, "load", lambda *args, **kwargs: view)
    client = TestClient(create_app(Settings(environment="test", data_dir=tmp_path)))

    response = client.get(
        "/api/market/industry-hierarchy",
        params={
            "data_snapshot_id": view.data_snapshot_id,
            "as_of": "2026-07-27",
            "parent_code": "801080.SI",
            "l2_code": "801081.SI",
            "instrument_id": "688981.SH",
        },
    )

    assert response.status_code == 200
    assert_stock_evidence_response(response.json())


def assert_stock_evidence_response(body: dict[str, Any]) -> None:
    assert body["weekly_candles"][0]["amount_cny"] == 2_000_000
    assert body["monthly_candles"][0]["trade_date"] == "2026-07-27"
    assert body["stock_evidence"]["fundamental"]["price_earnings_ttm"] == 20
    assert body["stock_evidence"]["fundamental_history"][0]["market_date"] == "2026-07-27"
    assert body["stock_evidence"]["shareholder_concentration"]["direction"] == "concentrating"
    assert body["stock_evidence"]["shareholder_concentration_history"][0]["holder_count"] == 900
