from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from astramind_mini.composition import create_app
from astramind_mini.config import Settings
from astramind_mini.trading_execution.adapters.paper_canary_store import (
    PaperCanaryAuthorizationStore,
)
from astramind_mini.trading_execution.domain import build_paper_canary_authorization

SHANGHAI = timezone(timedelta(hours=8))


def test_operations_api_is_read_only_and_redacted(tmp_path: Path) -> None:
    database = tmp_path / "paper.sqlite3"
    authorization = build_paper_canary_authorization(
        source_portfolio_target_id="portfolio-target:approved",
        source_shadow_order_plan_id="order-plan:shadow",
        account_baseline_id="paper-account-baseline:readonly",
        instrument_id="605208.SH",
        quantity=100,
        max_notional_cny=50_000,
        mandate_start=datetime(2099, 7, 29, 9, 30, tzinfo=SHANGHAI),
        mandate_end=datetime(2099, 7, 29, 10, 0, tzinfo=SHANGHAI),
        submission_start=datetime(2099, 7, 29, 9, 35, tzinfo=SHANGHAI),
        submission_end=datetime(2099, 7, 29, 9, 45, tzinfo=SHANGHAI),
        approved_at=datetime(2026, 7, 28, 12, 30, tzinfo=SHANGHAI),
    )
    PaperCanaryAuthorizationStore(database).publish(authorization)
    baseline = {
        "baseline_id": "paper-account-baseline:readonly",
        "startup_state": "readonly_ready",
        "inherited_position_count": 1,
        "open_order_fingerprints": [],
    }
    with sqlite3.connect(database) as connection:
        connection.execute(
            "INSERT INTO paper_account_baselines VALUES (?, ?, ?, ?, ?, ?)",
            (
                baseline["baseline_id"],
                "account-snapshot:redacted",
                "readonly_ready",
                "sha256:" + "a" * 64,
                json.dumps(baseline),
                "2026-07-28T04:00:00+00:00",
            ),
        )
    client = TestClient(create_app(Settings(environment="test", shadow_db_path=database)))

    response = client.get("/api/execution/paper-operations")

    assert response.status_code == 200
    body = response.json()
    assert body["instrument_id"] == "605208.SH"
    assert body["max_notional_cny"] == 50_000
    assert body["broker_actions_allowed"] is False
    assert body["blocker_codes"] == [
        "final_limit_approval_required",
        "fresh_limit_proposal_required",
    ]
    serialized = response.text.lower()
    assert all(term not in serialized for term in ("account_id", "userdata", "token", "secret"))
