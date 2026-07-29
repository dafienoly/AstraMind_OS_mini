from datetime import UTC, date, datetime
from pathlib import Path

from fastapi.testclient import TestClient

from astramind_mini.composition import create_app
from astramind_mini.config import Settings
from astramind_mini.data.adapters import DailyPipelineStore
from astramind_mini.data.contracts import DailyPipelineStatus
from astramind_mini.local_ops.contracts import DailyDecisionStatus
from astramind_mini.local_ops.daily_decision_store import DailyDecisionStore

NOW = datetime(2026, 7, 28, 18, tzinfo=UTC)
HASH = "sha256:" + "1" * 64


def test_daily_status_api_is_read_only_and_exposes_recovery_state(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "data"
    control = tmp_path / "control.sqlite3"
    local_ops = tmp_path / "local-ops.sqlite3"
    pipeline = DailyPipelineStatus(
        run_id="daily-pipeline:test",
        target_date=date(2026, 7, 28),
        base_snapshot_id="snapshot:test",
        state="waiting_provider",
        current_step="provider_collect",
        attempt=1,
        expected_l1_count=31,
        expected_l2_count=124,
        blocker_codes=("industry_daily_incomplete",),
        recovery_action="提供方完整后重跑",
        started_at=NOW,
        updated_at=NOW,
        content_hash=HASH,
    )
    DailyPipelineStore(control, data_root).publish_status(pipeline)
    decision = DailyDecisionStatus(
        run_id="daily-decision:test",
        pipeline_commit_id="daily-pipeline-commit:test",
        signal_date=date(2026, 7, 27),
        state="current",
        feature_snapshot_id="feature:test",
        prediction_batch_id="prediction:test",
        portfolio_target_id="target:test",
        order_plan_id="order-plan:test",
        shadow_preflight_state="ready",
        paper_preflight_state="ready",
        started_at=NOW,
        updated_at=NOW,
        completed_at=NOW,
        content_hash=HASH,
    )
    DailyDecisionStore(local_ops, tmp_path / "decision").publish_status(decision)
    client = TestClient(
        create_app(
            Settings(
                environment="test",
                data_dir=data_root,
                control_db_path=control,
                local_ops_db_path=local_ops,
            )
        )
    )

    pipeline_response = client.get("/api/system/daily-pipeline")
    decision_response = client.get("/api/system/daily-decision")
    operations_response = client.get("/api/system/daily-operations")

    assert pipeline_response.status_code == 200
    assert pipeline_response.json()["state"] == "waiting_provider"
    assert decision_response.status_code == 200
    assert decision_response.json()["paper_dispatch_state"] == "disabled"
    assert decision_response.json()["broker_actions_allowed"] is False
    assert operations_response.status_code == 200
    assert operations_response.json()["pipeline"]["state"] == "waiting_provider"
    assert operations_response.json()["schedule"]["state"] == "not_installed"
    assert operations_response.json()["broker_actions_allowed"] is False
    serialized = pipeline_response.text + decision_response.text + operations_response.text
    assert all(secret not in serialized.lower() for secret in ("token", "account_id", "userdata"))


def test_daily_run_request_is_local_idempotent_and_never_executes_work(
    tmp_path: Path,
) -> None:
    settings = Settings(
        environment="test",
        data_dir=tmp_path / "data",
        control_db_path=tmp_path / "control.sqlite3",
        local_ops_db_path=tmp_path / "local-ops.sqlite3",
        web_port=5174,
    )
    client = TestClient(create_app(settings))
    body = {"action": "run", "target_date": "2026-07-28"}
    headers = {
        "Origin": "http://127.0.0.1:5174",
        "X-AstraMind-Local-Action": "daily-ops-v1",
    }

    first = client.post("/api/system/daily-run-requests", json=body, headers=headers)
    duplicate = client.post("/api/system/daily-run-requests", json=body, headers=headers)
    rejected = client.post("/api/system/daily-run-requests", json=body)

    assert first.status_code == 200
    assert duplicate.status_code == 200
    assert first.json()["request_id"] == duplicate.json()["request_id"]
    assert first.json()["state"] == "pending"
    assert first.json()["broker_actions_allowed"] is False
    assert rejected.status_code == 403
    projection = client.get("/api/system/daily-operations").json()
    assert projection["pending_request"]["request_id"] == first.json()["request_id"]
    assert not (tmp_path / "data" / "current").exists()
