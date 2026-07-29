from datetime import UTC, date, datetime
from pathlib import Path

from fastapi.testclient import TestClient
from pytest import MonkeyPatch

from astramind_mini.composition import create_app
from astramind_mini.config import Settings
from astramind_mini.market_regime.adapters import SnapshotEtfRotation
from astramind_mini.market_regime.contracts import (
    EtfFunnel,
    EtfReplaySummary,
    EtfRotationProjection,
    EtfTargetDraft,
)


def test_etf_rotation_api_is_read_only_and_exposes_blocked_research(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        SnapshotEtfRotation, "current", lambda self, selected_etf_code=None: _view()
    )
    client = TestClient(
        create_app(
            Settings(
                data_dir=tmp_path,
                control_db_path=tmp_path / "control.db",
                local_ops_db_path=tmp_path / "ops.db",
                shadow_db_path=tmp_path / "shadow.db",
            )
        )
    )

    response = client.get("/api/market/etf-rotation")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "blocked"
    assert payload["target_draft"]["cash_weight"] == 1.0
    assert payload["target_draft"]["portfolio_target_created"] is False
    assert payload["target_draft"]["order_plan_created"] is False
    assert payload["broker_actions_allowed"] is False


def _view() -> EtfRotationProjection:
    return EtfRotationProjection(
        status="blocked",
        rotation_snapshot_id="etf-rotation:test",
        data_snapshot_id="snapshot:test",
        as_of=datetime(2026, 7, 29, 8, 44, tzinfo=UTC),
        evidence_cutoff=date(2026, 7, 28),
        strategy_version="etf-rotation-research-v1.0.0",
        mapping_version="sw2021-l1-etf-mapping-v1.0.0",
        spread_proxy_threshold_bps=35,
        tracking_proxy_threshold=0.12,
        funnel=EtfFunnel(
            industry_count=31,
            exact_mapping_count=0,
            foundation_count=0,
            evidence_gate_count=0,
            eligible_count=0,
        ),
        target_draft=EtfTargetDraft(
            status="cash_only",
            cash_weight=1,
            max_gross_weight=0.6,
        ),
        replay=EtfReplaySummary(
            status="candidate_frozen",
            evidence_label="候选冻结历史回放不可用于晋级",
        ),
        known_gaps=("mapping_not_effective_at_as_of",),
    )
