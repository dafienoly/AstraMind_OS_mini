from pathlib import Path

from fastapi.testclient import TestClient

from astramind_mini.composition import create_app
from astramind_mini.config import Settings


def test_model_status_api_reports_readonly_fallbacks_without_provider_calls(
    tmp_path: Path,
) -> None:
    client = TestClient(
        create_app(
            Settings(
                environment="test",
                data_dir=tmp_path / "data",
                market_model_dir=tmp_path / "models",
                control_db_path=tmp_path / "control.db",
                local_ops_db_path=tmp_path / "ops.db",
                shadow_db_path=tmp_path / "shadow.db",
            )
        )
    )

    response = client.get("/api/market/model-status")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload["models"]) == 5
    assert {item["state"] for item in payload["models"]} == {"fallback_v1"}
    assert all(item["reason_codes"] == ["v2_not_trained"] for item in payload["models"])
    assert payload["broker_actions_allowed"] is False
    assert "account" not in response.text.lower()
    assert "order_plan" not in response.text.lower()
