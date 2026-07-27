from fastapi.testclient import TestClient

from astramind_mini.composition import create_app
from astramind_mini.config import Settings


def test_health_endpoint_is_local_diagnostic_without_sensitive_state() -> None:
    client = TestClient(create_app(Settings(environment="test")))

    response = client.get("/healthz")
    payload = response.json()

    assert response.status_code == 200
    assert payload["status"] == "ready"
    assert payload["broker_enabled"] is False
    assert "token" not in response.text.lower()
    assert "account" not in response.text.lower()
