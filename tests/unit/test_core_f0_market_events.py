from __future__ import annotations

import json
from pathlib import Path

import pytest

from astramind_mini.strategy_research.core import FeatureAvailabilityState
from astramind_mini.strategy_research.core.f0 import evaluate_astramind_f0
from tests.unit.test_core_f0_unit import INSTRUMENTS, _bundle, _row

EDGE = json.loads(Path("tests/fixtures/core/f0/golden_case.json").read_text(encoding="utf-8"))[
    "edge_case_expectations"
]


def test_suspension_and_zero_amount_keep_the_session_but_block_amihud() -> None:
    bundle = _bundle()
    target = INSTRUMENTS[0]
    event_day = bundle.common_sessions[-10]
    previous_day = bundle.common_sessions[-11]
    previous_close = next(
        float(bar.research_close)
        for bar in bundle.market_bars
        if bar.instrument_id == target and bar.market_date == previous_day
    )
    suspended = tuple(
        bar.model_copy(
            update={
                "research_close": previous_close,
                "raw_close": previous_close,
                "amount_cny": 0.0,
                "turnover_rate": 0.0,
                "trading_state": "suspended",
            }
        )
        if bar.instrument_id == target and bar.market_date == event_day
        else bar
        for bar in bundle.market_bars
    )
    envelope = evaluate_astramind_f0(bundle.model_copy(update={"market_bars": suspended}))
    amihud = _row(envelope, target, "AMIHUD_20")
    assert [amihud.availability_state.value, amihud.missing_reason_code] == (
        EDGE["suspended_zero_amount_amihud"]
    )
    assert (
        _row(envelope, target, "LOG_MEDIAN_AMOUNT_20").availability_state
        == FeatureAvailabilityState.OBSERVED
    )


def test_missing_bar_does_not_compress_the_common_session_window() -> None:
    bundle = _bundle()
    target = INSTRUMENTS[0]
    event_day = bundle.common_sessions[-10]
    bars = tuple(
        bar
        for bar in bundle.market_bars
        if not (bar.instrument_id == target and bar.market_date == event_day)
    )
    envelope = evaluate_astramind_f0(bundle.model_copy(update={"market_bars": bars}))
    realized = _row(envelope, target, "REALIZED_VOL_20")
    assert [realized.availability_state.value, realized.missing_reason_code] == (
        EDGE["missing_bar_realized_vol"]
    )


def test_price_limit_and_corporate_action_audit_fields_do_not_replace_research_price() -> None:
    bundle = _bundle()
    target = INSTRUMENTS[0]
    final_day = bundle.common_sessions[-1]
    previous_close = next(
        float(bar.research_close)
        for bar in bundle.market_bars
        if bar.instrument_id == target and bar.market_date == bundle.common_sessions[-2]
    )
    limit_close = previous_close * 1.1
    limit_bars = tuple(
        bar.model_copy(
            update={
                "research_close": limit_close,
                "raw_close": limit_close,
                "trading_state": "price_limit",
            }
        )
        if bar.instrument_id == target and bar.market_date == final_day
        else bar
        for bar in bundle.market_bars
    )
    limit = evaluate_astramind_f0(bundle.model_copy(update={"market_bars": limit_bars}))
    assert _row(limit, target, "REV_5").value_raw == pytest.approx(EDGE["price_limit_rev_5"])

    action_bars = tuple(
        bar.model_copy(
            update={
                "raw_close": float(bar.research_close) / 2,
                "corporate_action_id": "split-audit-event",
            }
        )
        if bar.instrument_id == target and bar.market_date == final_day
        else bar
        for bar in bundle.market_bars
    )
    action = evaluate_astramind_f0(bundle.model_copy(update={"market_bars": action_bars}))
    assert _row(action, target, "REV_5").value_raw == pytest.approx(
        EDGE["corporate_action_continuous_rev_5"]
    )
