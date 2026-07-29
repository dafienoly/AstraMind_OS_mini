from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def test_daily_run_status_is_local_and_broker_free(tmp_path: Path) -> None:
    repository = Path(__file__).resolve().parents[2]
    environment = os.environ.copy()
    environment["ASTRAMIND_LOCAL_OPS_DB_PATH"] = str(tmp_path / "local-ops.sqlite3")
    environment["ASTRAMIND_ENVIRONMENT"] = "test"

    completed = subprocess.run(
        [sys.executable, "scripts/run_daily.py", "--status"],
        cwd=repository,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert completed.returncode == 0
    assert "state=waiting_window" in completed.stdout
    assert "broker_actions_allowed=false" in completed.stdout
    assert "MiniQMT" not in completed.stdout
