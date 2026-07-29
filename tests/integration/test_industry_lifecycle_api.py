from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from astramind_mini.composition import create_app
from astramind_mini.config import Settings
from astramind_mini.market_regime.adapters import SnapshotIndustryLifecycle
from astramind_mini.market_regime.contracts import (
    IndustryLifecyclePoint,
    IndustryLifecycleProjection,
    LifecycleTrajectoryPoint,
)


def test_lifecycle_api_serializes_read_only_projection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    projection = IndustryLifecycleProjection(
        status="ready",
        data_snapshot_id="snapshot:sha256:" + "8" * 64,
        as_of=datetime(2026, 7, 29, 2, tzinfo=UTC),
        evidence_cutoff=date(2026, 7, 28),
        taxonomy_version="SW2021",
        method_version="lifecycle-structure-v1.0.0",
        industries=(
            IndustryLifecyclePoint(
                industry_code="801080.SI",
                industry_name="电子",
                stage="强势扩散",
                confidence="high",
                strong_participation=31.5,
                low_participation=12.5,
                strong_change_5d=4.2,
                low_change_5d=-3.1,
                strong_peak_20d=33.0,
                strong_drawdown_20d=1.5,
                amount_share_20d=0.12,
                eligible_member_count=100,
                valid_member_count=90,
                coverage_ratio=0.9,
                trajectory=(
                    LifecycleTrajectoryPoint(
                        trade_date=date(2026, 7, 28),
                        strong_participation=31.5,
                        low_participation=12.5,
                    ),
                ),
            ),
        ),
    )
    monkeypatch.setattr(SnapshotIndustryLifecycle, "current", lambda self: projection)

    response = TestClient(create_app(Settings(environment="test", data_dir=tmp_path))).get(
        "/api/market/industry-lifecycle"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["data_snapshot_id"] == projection.data_snapshot_id
    assert body["industries"][0]["stage"] == "强势扩散"
    assert body["industries"][0]["trajectory"][0]["trade_date"] == "2026-07-28"
    serialized = response.text.lower()
    assert all(
        forbidden not in serialized
        for forbidden in ("order_plan", "broker", "account_id", "paper", "live")
    )


def test_lifecycle_api_reports_missing_snapshot(tmp_path: Path) -> None:
    response = TestClient(create_app(Settings(environment="test", data_dir=tmp_path))).get(
        "/api/market/industry-lifecycle"
    )

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "industry_lifecycle_snapshot_not_available"
