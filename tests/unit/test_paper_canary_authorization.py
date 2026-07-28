from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from astramind_mini.trading_execution.adapters.paper_canary_store import (
    PaperCanaryAuthorizationStore,
)
from astramind_mini.trading_execution.contracts.paper_canary import (
    PaperCanaryAuthorization,
)
from astramind_mini.trading_execution.domain.paper_canary import (
    build_paper_canary_authorization,
)

SHANGHAI = "+08:00"


def _time(value: str) -> datetime:
    return datetime.fromisoformat(value + SHANGHAI)


def _authorization() -> PaperCanaryAuthorization:
    return build_paper_canary_authorization(
        source_portfolio_target_id="portfolio-target:approved",
        source_shadow_order_plan_id="order-plan:shadow",
        account_baseline_id="paper-account-baseline:readonly",
        instrument_id="605208.SH",
        quantity=100,
        max_notional_cny=50_000,
        mandate_start=_time("2026-07-29T09:30:00"),
        mandate_end=_time("2026-07-29T10:00:00"),
        submission_start=_time("2026-07-29T09:35:00"),
        submission_end=_time("2026-07-29T09:45:00"),
        approved_at=_time("2026-07-28T12:30:00"),
    )


def test_authorization_is_deterministic_and_keeps_broker_frozen() -> None:
    first = _authorization()
    second = _authorization()
    assert first == second
    assert first.broker_actions_allowed is False
    assert first.final_numeric_limit_approval_required is True
    assert first.max_notional_cny == 50_000
    with pytest.raises(ValidationError):
        first.quantity = 200


@pytest.mark.parametrize(
    ("instrument", "quantity", "maximum"),
    [
        ("688636.SH", 100, 50_000),
        ("605208.SH", 50, 50_000),
        ("605208.SH", 100, 50_001),
    ],
)
def test_authorization_rejects_canary_scope_expansion(
    instrument: str, quantity: int, maximum: int
) -> None:
    with pytest.raises((ValueError, ValidationError)):
        build_paper_canary_authorization(
            source_portfolio_target_id="portfolio-target:approved",
            source_shadow_order_plan_id="order-plan:shadow",
            account_baseline_id="paper-account-baseline:readonly",
            instrument_id=instrument,
            quantity=quantity,
            max_notional_cny=maximum,
            mandate_start=_time("2026-07-29T09:30:00"),
            mandate_end=_time("2026-07-29T10:00:00"),
            submission_start=_time("2026-07-29T09:35:00"),
            submission_end=_time("2026-07-29T09:45:00"),
            approved_at=_time("2026-07-28T12:30:00"),
        )


def test_window_must_be_inside_mandate() -> None:
    with pytest.raises(ValidationError, match="提交窗口"):
        build_paper_canary_authorization(
            source_portfolio_target_id="portfolio-target:approved",
            source_shadow_order_plan_id="order-plan:shadow",
            account_baseline_id="paper-account-baseline:readonly",
            instrument_id="605208.SH",
            quantity=100,
            max_notional_cny=50_000,
            mandate_start=_time("2026-07-29T09:30:00"),
            mandate_end=_time("2026-07-29T09:40:00"),
            submission_start=_time("2026-07-29T09:35:00"),
            submission_end=_time("2026-07-29T09:45:00"),
            approved_at=_time("2026-07-28T12:30:00"),
        )


def test_append_only_store_round_trip(tmp_path: Path) -> None:
    store = PaperCanaryAuthorizationStore(tmp_path / "paper.sqlite3")
    value = _authorization()
    store.publish(value)
    store.publish(value)
    assert store.read(value.authorization_id) == value
