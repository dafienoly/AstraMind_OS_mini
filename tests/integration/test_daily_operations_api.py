from pathlib import Path

from fastapi.testclient import TestClient

from astramind_mini.composition import create_app
from astramind_mini.config import Settings


def test_daily_operations_empty_projection_is_explicit_and_broker_free(
    tmp_path: Path,
) -> None:
    client = TestClient(create_app(_settings(tmp_path)))

    response = client.get("/api/system/daily-operations")

    assert response.status_code == 200
    payload = response.json()
    assert payload["latest_run"] is None
    assert payload["schedule"]["state"] == "not_installed"
    assert {item["code"] for item in payload["attention"]} == {
        "daily_schedule_not_installed",
        "daily_run_not_started",
    }
    assert payload["broker_actions_allowed"] is False


def test_local_run_request_is_source_checked_and_idempotent(tmp_path: Path) -> None:
    client = TestClient(create_app(_settings(tmp_path)))
    body = {"action": "run", "target_date": "2026-07-28"}
    headers = {
        "Origin": "http://127.0.0.1:5174",
        "X-AstraMind-Local-Action": "daily-ops-v1",
    }

    first = client.post("/api/system/daily-run-requests", json=body, headers=headers)
    duplicate = client.post("/api/system/daily-run-requests", json=body, headers=headers)
    rejected = client.post("/api/system/daily-run-requests", json=body)

    assert first.status_code == duplicate.status_code == 200
    assert first.json()["request_id"] == duplicate.json()["request_id"]
    assert first.json()["broker_actions_allowed"] is False
    assert rejected.status_code == 403
    assert not (tmp_path / "data" / "current").exists()


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        environment="test",
        data_dir=tmp_path / "data",
        control_db_path=tmp_path / "control.sqlite3",
        local_ops_db_path=tmp_path / "local-ops.sqlite3",
        shadow_db_path=tmp_path / "shadow.sqlite3",
        web_port=5174,
    )
