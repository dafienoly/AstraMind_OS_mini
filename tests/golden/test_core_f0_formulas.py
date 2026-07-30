from __future__ import annotations

import json
import math
from collections.abc import Sequence
from itertools import pairwise
from pathlib import Path
from statistics import fmean, median, stdev

import numpy as np
import pytest

from astramind_mini.strategy_research.application.identity import research_hash
from astramind_mini.strategy_research.core import (
    CoreRawFeatureRowDraft,
    FeatureAvailabilityState,
    build_core_raw_feature_envelope,
)
from astramind_mini.strategy_research.core.f0 import (
    F0_FULL_DEFINITION_MANIFEST_HASH,
    evaluate_astramind_f0,
)
from astramind_mini.strategy_research.core.packages import ASTRAMIND_F0, ASTRAMIND_F0_FEATURE_ORDER
from tests.unit.test_core_f0_unit import INDUSTRIES, INSTRUMENTS, _bundle

FIXTURE = Path("tests/fixtures/core/f0/golden_case.json")
OBSERVED = FeatureAvailabilityState.OBSERVED
MISSING = FeatureAvailabilityState.MISSING
NOT_APPLICABLE = FeatureAvailabilityState.NOT_APPLICABLE


def _draft(
    bundle,
    instrument: str,
    feature: str,
    *,
    value: float | None = None,
    state: FeatureAvailabilityState = OBSERVED,
    reason: str | None = None,
) -> CoreRawFeatureRowDraft:
    return CoreRawFeatureRowDraft(
        instrument_id=instrument,
        decision_time=bundle.core_input.cutoff_at,
        feature_definition_id=feature,
        feature_definition_version="1.0.0",
        value_raw=value,
        availability_state=state,
        missing_reason_code=reason,
    )


def _financial_oracle(bundle, instrument: str) -> tuple[CoreRawFeatureRowDraft, ...]:
    financial_ids = ASTRAMIND_F0_FEATURE_ORDER[:13]
    index = INSTRUMENTS.index(instrument)
    if index in {1, 2, 3}:
        return tuple(
            _draft(bundle, instrument, feature, state=NOT_APPLICABLE,
                   reason="f0_financial_not_applicable")
            for feature in financial_ids
        )
    if index in {4, 5}:
        reasons = {
            feature: (
                "f0_dividend_input_missing" if feature == "DY_TTM" else "f0_financial_input_missing"
            )
            for feature in financial_ids
        }
        return tuple(
            _draft(bundle, instrument, feature, state=MISSING,
                   reason=reasons[feature])
            for feature in financial_ids
        )

    close = _closes(bundle, instrument)[-1]
    values = {
        "EP_TTM": 141 / 10_000_000_000,
        "BP": 900 / 10_000_000_000,
        "SP_TTM": 1410 / 10_000_000_000,
        "DY_TTM": 0.5 / close,
        "ROE_TTM": 141 / ((900 + 800) / 2),
        "ROA_TTM": 155.1 / ((2000 + 1800) / 2),
        "OPERATING_MARGIN_TTM": 211.5 / 1410,
        "OCF_TO_NET_INCOME_TTM": 169.2 / 155.1,
        "ACCRUALS_TO_ASSETS_TTM": (155.1 - 169.2) / 1900,
        "DEBT_TO_ASSETS": 1100 / 2000,
        "REVENUE_TTM_YOY": 1410 / 1140 - 1,
        "NET_PROFIT_TTM_YOY": 141 / 114 - 1,
        "OCF_TTM_YOY": 169.2 / 136.8 - 1,
    }
    return tuple(
        _draft(bundle, instrument, feature, value=values[feature]) for feature in financial_ids
    )


def _market_oracle(bundle, instrument: str) -> tuple[CoreRawFeatureRowDraft, ...]:
    sessions = bundle.common_sessions
    closes = _closes(bundle, instrument)
    simple_returns = [closes[index] / closes[index - 1] - 1 for index in range(1, len(closes))]
    amounts = [
        float(item.amount_cny)
        for item in bundle.market_bars
        if item.instrument_id == instrument and item.amount_cny is not None
    ]
    turnover = [
        float(item.turnover_rate)
        for item in bundle.market_bars
        if item.instrument_id == instrument and item.turnover_rate is not None
    ]
    values = {
        "MOM_20_5": closes[-6] / closes[-21] - 1,
        "MOM_60_5": closes[-6] / closes[-61] - 1,
        "MOM_120_20": closes[-21] / closes[-121] - 1,
        "INDUSTRY_REL_MOM_60_5": _industry_relative_oracle(bundle, instrument, sessions),
        "REV_5": -(closes[-1] / closes[-6] - 1),
        "RESIDUAL_REV_20": _residual_oracle(bundle, instrument, sessions),
        "REALIZED_VOL_20": math.sqrt(252)
        * stdev(math.log1p(value) for value in simple_returns[-20:]),
        "DOWNSIDE_VOL_60": math.sqrt(
            252 * fmean(min(value, 0) ** 2 for value in simple_returns[-60:])
        ),
        "LOG_MEDIAN_AMOUNT_20": math.log1p(median(amounts[-20:])),
        "TURNOVER_MEAN_20": fmean(turnover[-20:]),
        "AMIHUD_20": math.log1p(
            1e8
            * fmean(
                abs(value) / amount
                for value, amount in zip(
                    simple_returns[-20:],
                    amounts[-20:],
                    strict=True,
                )
            )
        ),
    }
    return tuple(
        _draft(bundle, instrument, feature, value=values[feature])
        for feature in ASTRAMIND_F0_FEATURE_ORDER[13:]
    )


def _closes(bundle, instrument: str) -> list[float]:
    return [
        float(item.research_close)
        for item in bundle.market_bars
        if item.instrument_id == instrument and item.research_close is not None
    ]


def _close_index(bundle) -> dict[tuple[str, object], float]:
    return {
        (item.instrument_id, item.market_date): float(item.research_close)
        for item in bundle.market_bars
        if item.research_close is not None
    }


def _industry_at(bundle, instrument: str, day) -> str | None:
    visible = [
        item
        for item in bundle.industry_memberships
        if item.instrument_id == instrument
        and item.valid_from <= day
        and (item.valid_to is None or item.valid_to >= day)
        and item.available_at.date() <= day
    ]
    return max(visible, key=lambda item: item.valid_from).sw_l1 if visible else None


def _members(bundle, day) -> tuple[str, ...]:
    return tuple(
        item.instrument_id
        for item in bundle.universe_decisions
        if item.decision_date == day and item.research_member
    )


def _cross_section(
    bundle,
    close_index: dict[tuple[str, object], float],
    previous_day,
    day,
    industry: str | None = None,
) -> list[float]:
    values: list[float] = []
    for member in _members(bundle, day):
        if industry is not None and _industry_at(bundle, member, day) != industry:
            continue
        values.append(close_index[(member, day)] / close_index[(member, previous_day)] - 1)
    return values


def _industry_relative_oracle(
    bundle,
    instrument: str,
    sessions: Sequence[object],
) -> float:
    close_index = _close_index(bundle)
    own = close_index[(instrument, sessions[-6])] / close_index[(instrument, sessions[-61])] - 1
    compounded = 1.0
    for previous_day, day in pairwise(sessions[-61:-5]):
        industry = _industry_at(bundle, instrument, day)
        assert industry is not None
        compounded *= 1 + fmean(_cross_section(bundle, close_index, previous_day, day, industry))
    return own - (compounded - 1)


def _residual_oracle(
    bundle,
    instrument: str,
    sessions: Sequence[object],
) -> float:
    close_index = _close_index(bundle)
    rows: list[tuple[float, float, float]] = []
    for previous_day, day in pairwise(sessions[-21:]):
        industry = _industry_at(bundle, instrument, day)
        assert industry is not None
        rows.append(
            (
                close_index[(instrument, day)] / close_index[(instrument, previous_day)] - 1,
                fmean(_cross_section(bundle, close_index, previous_day, day)),
                fmean(
                    _cross_section(
                        bundle,
                        close_index,
                        previous_day,
                        day,
                        industry,
                    )
                ),
            )
        )
    y = np.asarray([row[0] for row in rows])
    x = np.column_stack(
        (
            np.ones(len(rows)),
            np.asarray([row[1] for row in rows]),
            np.asarray([row[2] for row in rows]),
        )
    )
    coefficients = np.linalg.lstsq(x, y, rcond=None)[0]
    return -float(np.sum(y - x @ coefficients))


def _oracle_rows(bundle) -> tuple[CoreRawFeatureRowDraft, ...]:
    return tuple(
        row
        for instrument in INSTRUMENTS
        for row in (
            *_financial_oracle(bundle, instrument),
            *_market_oracle(bundle, instrument),
        )
    )


def _row_fingerprint(rows: Sequence[CoreRawFeatureRowDraft]) -> str:
    return research_hash(
        tuple(
            (
                row.feature_definition_id,
                row.availability_state.value,
                row.value_raw,
                row.missing_reason_code,
            )
            for row in rows
        )
    )


def test_f0_260_session_golden_uses_independent_full_row_oracle() -> None:
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    bundle = _bundle(len(fixture["common_sessions"]))
    oracle_rows = _oracle_rows(bundle)
    oracle_envelope = build_core_raw_feature_envelope(
        core_input=bundle.core_input,
        package_spec=ASTRAMIND_F0,
        computation_manifest_hash=fixture["full_definition_manifest_hash"],
        calculation_sessions=bundle.common_sessions,
        feature_order=ASTRAMIND_F0_FEATURE_ORDER,
        rows=oracle_rows,
    )
    actual = evaluate_astramind_f0(bundle)

    assert fixture["oracle"]["kind"] == "independent-hand-formula-and-state-oracle"
    provenance = fixture["provenance"]
    assert provenance["generator_identity"] == "tests/golden/test_core_f0_formulas.py::_oracle_rows"
    assert provenance["input_builder_identity"] == "tests/unit/test_core_f0_unit.py::_bundle"
    assert provenance["generator_version"] == "astramind-f0-independent-oracle-v1.0.0"
    assert provenance["generator_process"] == (
        "reviewed deterministic in-test oracle; no standalone generator; "
        "production evaluator is excluded from expected-row derivation"
    )
    assert provenance["authoritative_source_commit"] == "37c83fd166fe050c1f2a843560d10a72665cea76"
    assert provenance["input_hash_schema"] == "astramind-f0-golden-complete-input-v1"
    expected_input_hash = research_hash(
        {"schema": provenance["input_hash_schema"], "f0_input_bundle": bundle}
    )
    assert provenance["complete_input_hash"] == expected_input_hash
    assert len(bundle.common_sessions) == 260
    assert len(INSTRUMENTS) == 6
    assert len(set(INDUSTRIES)) == 3
    assert INSTRUMENTS[-1] not in _members(bundle, bundle.common_sessions[0])
    assert INSTRUMENTS[-1] in _members(bundle, bundle.common_sessions[60])
    assert fixture["edge_case_expectations"]["new_stock_pre_entry_excluded_from_historical_u0"]
    assert _industry_at(bundle, INSTRUMENTS[-1], bundle.common_sessions[100]) == (INDUSTRIES[-1])
    assert _industry_at(bundle, INSTRUMENTS[-1], bundle.common_sessions[160]) == (INDUSTRIES[1])
    industry_row = next(
        row
        for row in oracle_rows
        if row.instrument_id == INSTRUMENTS[-1]
        and row.feature_definition_id == "INDUSTRY_REL_MOM_60_5"
    )
    assert (
        industry_row.availability_state.value
        == (fixture["edge_case_expectations"]["industry_change_market_state"])
    )
    assert len(oracle_rows) == len(actual.rows) == 144
    assert fixture["full_definition_manifest_hash"] == F0_FULL_DEFINITION_MANIFEST_HASH
    assert oracle_envelope.feature_snapshot.content_hash == fixture["expected_output_hash"]
    assert oracle_envelope.manifest.rows_content_hash == fixture["expected_rows_content_hash"]
    assert actual.feature_snapshot.content_hash == oracle_envelope.feature_snapshot.content_hash
    assert actual.manifest.rows_content_hash == oracle_envelope.manifest.rows_content_hash
    assert (
        actual.manifest.observed_count,
        actual.manifest.missing_count,
        actual.manifest.not_applicable_count,
    ) == tuple(fixture["expected_state_counts"])

    for instrument in INSTRUMENTS:
        expected_rows = tuple(row for row in oracle_rows if row.instrument_id == instrument)
        actual_rows = tuple(row for row in actual.rows if row.instrument_id == instrument)
        assert (
            _row_fingerprint(expected_rows)
            == (fixture["expected_instrument_row_hashes"][instrument])
        )
        for expected, observed in zip(expected_rows, actual_rows, strict=True):
            assert observed.feature_definition_id == expected.feature_definition_id
            assert observed.availability_state == expected.availability_state
            assert observed.missing_reason_code == expected.missing_reason_code
            if expected.value_raw is None:
                assert observed.value_raw is None
            else:
                tolerance = 1e-9 if expected.feature_definition_id == "RESIDUAL_REV_20" else 1e-12
                assert observed.value_raw == pytest.approx(
                    expected.value_raw,
                    abs=tolerance,
                    rel=tolerance,
                )
