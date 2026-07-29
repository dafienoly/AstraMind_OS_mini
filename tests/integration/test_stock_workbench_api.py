from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from astramind_mini.composition import create_app
from astramind_mini.config import Settings
from astramind_mini.market_regime.adapters import SnapshotStockWorkbench
from astramind_mini.market_regime.contracts import (
    CompletedStockMarketEvidence,
    EvidenceSectionIdentity,
    PriceCandle,
    ShareholderConcentrationEvidence,
    StockEvidence,
    StockIndustryContext,
    StockInspectionFocus,
    StockInstrumentIdentity,
    StockWorkbenchProjection,
)


def test_stock_workbench_api_preserves_focus_and_same_snapshot_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    projection = _projection()
    monkeypatch.setattr(
        SnapshotStockWorkbench,
        "load",
        lambda self, *args, **kwargs: projection,
    )
    response = TestClient(create_app(Settings(environment="test", data_dir=tmp_path))).get(
        "/api/market/stocks/000001.sz",
        params={
            "origin": "industry_rotation",
            "mode": "sealed_evidence",
            "return_target": "industry_rotation",
            "data_snapshot_id": projection.focus.data_snapshot_id,
            "as_of": "2026-07-28",
            "industry_code": "801780.SI",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["focus"]["origin"] == "industry_rotation"
    assert body["focus"]["data_snapshot_id"] == projection.focus.data_snapshot_id
    assert body["completed_market_evidence"]["evidence"]["provider"] == "miniqmt"
    assert body["realtime_market_overlay"] is None
    assert all(
        forbidden not in response.text.lower()
        for forbidden in ("order_plan", "account_id", "place_order", "cancel_order")
    )


def _projection() -> StockWorkbenchProjection:
    snapshot_id = "snapshot:sha256:" + "1" * 64
    evidence = EvidenceSectionIdentity(
        state="ready",
        as_of=date(2026, 7, 28),
        provider="miniqmt",
        content_identity="sha256:" + "2" * 64,
    )
    candle = PriceCandle(
        trade_date=date(2026, 7, 28),
        open=10,
        high=11,
        low=9,
        close=10.5,
        volume_lots=100,
        amount_cny=1_000_000,
    )
    return StockWorkbenchProjection(
        focus=StockInspectionFocus(
            focus_id="sha256:" + "3" * 64,
            instrument_id="000001.SZ",
            origin="industry_rotation",
            as_of=date(2026, 7, 28),
            data_snapshot_id=snapshot_id,
            industry_code="801780.SI",
            mode="sealed_evidence",
            return_target="industry_rotation",
            created_at=datetime(2026, 7, 29, tzinfo=UTC),
        ),
        instrument_identity=StockInstrumentIdentity(
            instrument_id="000001.SZ",
            instrument_name="平安银行",
            exchange="SZ",
            market="主板",
        ),
        completed_market_evidence=CompletedStockMarketEvidence(
            evidence=evidence,
            daily=(candle,),
            weekly=(candle,),
            monthly=(candle,),
        ),
        industry_context=StockIndustryContext(
            evidence=evidence,
            taxonomy="SW",
            taxonomy_version="SW2021",
            l1_code="801780.SI",
            l1_name="银行",
        ),
        stock_evidence=StockEvidence(
            instrument_id="000001.SZ",
            instrument_name="平安银行",
            as_of=date(2026, 7, 28),
            shareholder_concentration=ShareholderConcentrationEvidence(
                status="unavailable",
            ),
        ),
        content_identity="sha256:" + "4" * 64,
    )
