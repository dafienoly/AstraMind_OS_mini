from pathlib import Path

from fastapi.testclient import TestClient

from astramind_mini.composition import create_app
from astramind_mini.config import Settings
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
