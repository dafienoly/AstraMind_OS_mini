from pathlib import Path

import pytest
from pydantic import ValidationError

from astramind_mini.config import Settings


def test_environment_overrides_env_file_and_secret_is_masked(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env_file = tmp_path / ".env.local"
    env_file.write_text(
        "ASTRAMIND_API_PORT=8100\nASTRAMIND_TUSHARE_TOKEN=local-placeholder\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ASTRAMIND_API_PORT", "8200")

    settings = Settings()

    assert settings.api_port == 8200
    assert settings.tushare_token is not None
    assert "local-placeholder" not in repr(settings)


def test_non_loopback_host_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(api_host="0.0.0.0")  # type: ignore[arg-type]
