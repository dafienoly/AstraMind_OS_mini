from __future__ import annotations

import ast
import inspect
import json
from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pytest

from astramind_mini.strategy_research.core.alpha158 import (
    ALPHA158_MANIFEST,
    EXPECTED_COMPUTATION_MANIFEST_HASH,
    FIELDS_SHA256,
    MISSING_REASON,
    NAMES_SHA256,
    PAIRS_SHA256,
    Alpha158BatchInput,
    Alpha158InputError,
    alpha158_computation_manifest_hash,
    build_alpha158_raw_envelope,
    calculate_alpha158,
    calculate_alpha158_in_chunks,
    definitions,
)
from astramind_mini.strategy_research.core.alpha158.calculator import (
    _calculate_instrument,
    _nonfinite_mask,
)
from astramind_mini.strategy_research.core.alpha158.definitions import (
    EXPECTED_FIELDS_SHA256,
    EXPECTED_NAMES_SHA256,
    EXPECTED_PAIRS_SHA256,
    QLIB_ALPHA158_FIELDS,
    QLIB_ALPHA158_NAMES,
    validate_frozen_manifest,
)
from astramind_mini.strategy_research.core.alpha158.regression import (
    rolling_residual,
    rolling_rsquare,
    rolling_slope,
)
from astramind_mini.strategy_research.core.alpha158.rolling import (
    rolling_corr,
    rolling_idxmax,
    rolling_idxmin,
    rolling_max,
    rolling_mean,
    rolling_min,
    rolling_quantile,
    rolling_rank,
    rolling_std,
    rolling_sum,
)
from astramind_mini.strategy_research.core.feature_values import (
    FeatureAvailabilityState,
)
from astramind_mini.strategy_research.core.packages import (
    QLIB_ALPHA158,
    QLIB_ALPHA158_FEATURE_ORDER,
)
from tests.unit.test_core_alpha158_support import (
    common_dates,
    delete_date,
    synthetic_batch,
)

FIXTURE = Path(__file__).parents[1] / "fixtures" / "core" / "alpha158"


def test_default_runtime_import_graph_excludes_forbidden_systems() -> None:
    package = (
        Path(__file__).parents[2]
        / "src"
        / "astramind_mini"
        / "strategy_research"
        / "core"
        / "alpha158"
    )
    imported: set[str] = set()
    for source in package.glob("*.py"):
        tree = ast.parse(source.read_text(encoding="utf-8"))
        imported.update(
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        )
        imported.update(
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module is not None
        )
    forbidden = {
        "qlib",
        "pandas",
        "scipy",
        "astramind_mini.data",
        "astramind_mini.portfolio_risk",
        "astramind_mini.trading_execution",
    }
    assert not {
        module
        for module in imported
        if any(module == prefix or module.startswith(f"{prefix}.") for prefix in forbidden)
    }


def test_manifest_is_the_exact_frozen_158_dimension_qlib_identity() -> None:
    validate_frozen_manifest()

    assert QLIB_ALPHA158_NAMES == QLIB_ALPHA158_FEATURE_ORDER
    assert len(QLIB_ALPHA158_NAMES) == len(set(QLIB_ALPHA158_NAMES)) == 158
    assert len(QLIB_ALPHA158_FIELDS) == 158
    assert NAMES_SHA256 == EXPECTED_NAMES_SHA256
    assert FIELDS_SHA256 == EXPECTED_FIELDS_SHA256
    assert PAIRS_SHA256 == EXPECTED_PAIRS_SHA256
    assert (
        alpha158_computation_manifest_hash()
        == EXPECTED_COMPUTATION_MANIFEST_HASH
        == "sha256:9c6871c861793952f6693e0c209b28a7179eb3df0c38d5e2a9ff40c6ddc5a5c6"
    )
    assert (
        ALPHA158_MANIFEST.required_definition_registry_hash
        == QLIB_ALPHA158.required_definition_registry_hash
        == "sha256:002151c6f808dc503b292caa604435f634d69672193288535f3fec504dd61c04"
    )
    assert QLIB_ALPHA158_FIELDS[:4] == (
        "($close-$open)/$open",
        "($high-$low)/$open",
        "($close-$open)/($high-$low+1e-12)",
        "($high-Greater($open, $close))/$open",
    )
    assert QLIB_ALPHA158_FIELDS[-1] == (
        "(Sum(Greater($volume-Ref($volume, 1), 0), 60)"
        "-Sum(Greater(Ref($volume, 1)-$volume, 0), 60))/"
        "(Sum(Abs($volume-Ref($volume, 1)), 60)+1e-12)"
    )


def test_qlib_warmup_rank_idx_boolean_and_zero_volume_quirks() -> None:
    batch = synthetic_batch()
    result = calculate_alpha158(batch)
    position = {name: index for index, name in enumerate(result.feature_names)}

    assert np.isnan(result.values[0, :60, position["ROC60"]]).all()
    assert np.isfinite(result.values[0, 60, position["ROC60"]])
    assert np.isfinite(result.values[0, 0, position["MA60"]])
    assert np.isnan(result.values[0, 0, position["STD60"]])
    assert result.values[0, 0, position["RANK60"]] == 1.0
    assert result.values[0, 0, position["IMAX60"]] == 1.0 / 60.0
    assert result.values[0, 0, position["IMIN60"]] == 1.0 / 60.0
    assert result.values[0, 0, position["CNTP60"]] == 0.0
    assert result.values[0, 0, position["CNTN60"]] == 0.0
    assert result.values[0, 0, position["CNTD60"]] == 0.0
    assert np.isnan(result.values[0, 0, position["SUMP60"]])
    assert np.isnan(result.values[0, 0, position["SUMN60"]])
    assert np.isnan(result.values[0, 0, position["SUMD60"]])
    assert result.values[0, 7, position["VMA60"]] > 1e15 and np.isfinite(
        result.values[0, 7, position["VMA60"]]
    )
    assert np.any(result.nonfinite_mask[:, :, position["CORD60"]] != 0)
    assert np.all(np.any(np.isfinite(result.values[:, 60:, :]), axis=(0, 1)))


def test_idx_operators_keep_raw_nan_argmax_and_earliest_ties() -> None:
    values = np.asarray([1.0, np.nan, 3.0, 3.0], dtype=np.float64)

    assert rolling_idxmax(values, 4)[-1] == 2.0
    assert rolling_idxmin(values, 4)[-1] == 2.0
    tied = np.asarray([1.0, 3.0, 3.0], dtype=np.float64)
    assert rolling_idxmax(tied, 3)[-1] == 2.0


def test_ordinary_rolling_ignores_signed_infinity_but_idx_keeps_raw_windows() -> None:
    values = np.asarray([1.0, np.inf, 3.0, -np.inf, 5.0], dtype=np.float64)

    np.testing.assert_array_equal(
        rolling_mean(values, 3),
        np.asarray([1.0, 1.0, 2.0, 3.0, 4.0]),
    )
    np.testing.assert_array_equal(
        rolling_sum(values, 3),
        np.asarray([1.0, 1.0, 4.0, 3.0, 8.0]),
    )
    np.testing.assert_allclose(
        rolling_std(values, 3),
        np.asarray([np.nan, np.nan, 2**0.5, np.nan, 2**0.5]),
        equal_nan=True,
    )
    np.testing.assert_array_equal(
        rolling_max(values, 3),
        np.asarray([1.0, 1.0, 3.0, 3.0, 5.0]),
    )
    np.testing.assert_array_equal(
        rolling_min(values, 3),
        np.asarray([1.0, 1.0, 1.0, 3.0, 3.0]),
    )
    np.testing.assert_allclose(
        rolling_quantile(values, 3, 0.8),
        np.asarray([1.0, 1.0, 2.6, 3.0, 4.6]),
    )
    np.testing.assert_array_equal(
        rolling_rank(values, 3),
        np.asarray([1.0, np.nan, 1.0, np.nan, 1.0]),
    )
    assert rolling_idxmax(values, 3)[-2] == 1.0
    assert rolling_idxmin(values, 3)[-2] == 3.0


def test_wvma_finite_positive_inputs_match_independent_overflow_oracle() -> None:
    oracle = json.loads((FIXTURE / "wvma_overflow_oracle.json").read_text(encoding="utf-8"))
    close = np.asarray(oracle["close"], dtype=np.float64)
    inputs = np.ones((len(close), 6), dtype=np.float64)
    inputs[:, :4] = close[:, None]
    inputs[:, 4] = np.asarray(oracle["volume_lots"], dtype=np.float64)
    inputs[:, 5] = np.asarray(oracle["vwap"], dtype=np.float64)

    with np.errstate(all="ignore"):
        intermediate = np.abs(close / np.roll(close, 1) - 1.0) * inputs[:, 4]
    intermediate[0] = np.nan
    assert np.isfinite(inputs).all() and np.all(inputs > 0.0)
    assert np.isposinf(intermediate[[1, 3]]).all()

    actual = _calculate_instrument(inputs)[:, int(oracle["feature_index"])]
    actual_mask = _nonfinite_mask(actual)
    expected = np.asarray(
        [np.nan if value is None else value for value in oracle["expected_values"]],
        dtype=np.float64,
    )
    np.testing.assert_array_equal(
        actual_mask,
        np.asarray(oracle["expected_nonfinite_mask"], dtype=np.uint8),
    )
    finite = actual_mask == 0
    np.testing.assert_allclose(actual[finite], expected[finite], rtol=1e-9, atol=1e-9)


def test_regression_keeps_time_gaps_and_correlation_applies_qlib_threshold() -> None:
    values = np.asarray([1.0, np.nan, 3.0, 4.0], dtype=np.float64)
    assert rolling_slope(values, 4)[-1] == pytest.approx(1.0)
    assert rolling_rsquare(values, 4)[-1] == pytest.approx(1.0)
    assert rolling_residual(values, 4)[-1] == pytest.approx(0.0)

    near_constant = np.asarray([1.0, 1.000001, 0.999999, 1.000002], dtype=np.float64)
    threshold_clear = np.asarray([1.0, 1.0001, 0.9999, 1.0002], dtype=np.float64)
    trend = np.asarray([1.0, 2.0, 3.0, 4.0], dtype=np.float64)
    assert np.isnan(rolling_corr(trend, near_constant, 4)[-1])
    assert np.isfinite(rolling_corr(trend, threshold_clear, 4)[-1])


def test_regression_cross_row_state_matches_compiled_qlib_counterexample() -> None:
    values = 10_000.0 + 0.0001 * np.arange(75, dtype=np.float64)
    expected = np.load(FIXTURE / "regression_counterexample.npy", allow_pickle=False)
    actual = np.stack(
        (
            rolling_slope(values, 5),
            rolling_rsquare(values, 5),
            rolling_residual(values, 5),
        )
    )

    np.testing.assert_array_equal(actual, expected)
    assert np.isinf(expected[1]).any()
    assert np.isnan(expected[1]).any()


def test_public_raw_envelope_masks_every_nonfinite_formula_result() -> None:
    result, envelope = build_alpha158_raw_envelope(synthetic_batch())
    result_positions = {
        instrument_id: index for index, instrument_id in enumerate(result.instrument_ids)
    }
    final_mask = np.asarray(
        [
            result.nonfinite_mask[
                result_positions[row.instrument_id],
                -1,
                result.feature_names.index(row.feature_definition_id),
            ]
            for row in envelope.rows
        ],
        dtype=np.uint8,
    )

    assert envelope.package_spec == QLIB_ALPHA158
    assert result.computation_manifest_hash == EXPECTED_COMPUTATION_MANIFEST_HASH
    assert envelope.manifest.computation_manifest_hash == result.computation_manifest_hash
    assert envelope.feature_order == QLIB_ALPHA158_FEATURE_ORDER
    assert envelope.manifest.row_count == 3 * 158
    assert envelope.manifest.not_applicable_count == 0
    assert envelope.manifest.missing_count == int(np.count_nonzero(final_mask))
    assert all(
        row.value_raw is None
        and row.availability_state == FeatureAvailabilityState.MISSING
        and row.missing_reason_code == MISSING_REASON
        for row, mask in zip(envelope.rows, final_mask, strict=True)
        if mask
    )
    assert all(row.value_raw is None or np.isfinite(row.value_raw) for row in envelope.rows)


def test_old_expression_only_manifest_hash_cannot_be_injected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert tuple(inspect.signature(build_alpha158_raw_envelope).parameters) == ("batch",)
    old_manifest_hash = f"sha256:{PAIRS_SHA256}"
    monkeypatch.setattr(
        definitions,
        "EXPECTED_COMPUTATION_MANIFEST_HASH",
        old_manifest_hash,
    )

    with pytest.raises(RuntimeError, match="computation manifest identity mismatch"):
        calculate_alpha158(synthetic_batch())


def test_future_append_and_repeated_calculation_preserve_existing_prefix() -> None:
    prefix = calculate_alpha158(synthetic_batch(65))
    full = calculate_alpha158(synthetic_batch(75))
    repeated = calculate_alpha158(synthetic_batch(75))
    chunked = calculate_alpha158_in_chunks(synthetic_batch(75), chunk_size=1)

    np.testing.assert_array_equal(prefix.values, full.values[:, :65, :])
    np.testing.assert_array_equal(
        prefix.nonfinite_mask,
        full.nonfinite_mask[:, :65, :],
    )
    assert repeated.content_hash == full.content_hash
    assert chunked.content_hash == full.content_hash
    assert repeated.values.tobytes() == full.values.tobytes()
    assert chunked.values.tobytes() == full.values.tobytes()
    assert repeated.nonfinite_mask.tobytes() == full.nonfinite_mask.tobytes()


def test_instrument_reordering_and_mutation_are_strictly_isolated() -> None:
    batch = synthetic_batch()
    baseline = calculate_alpha158(batch)
    reordered_batch = Alpha158BatchInput(
        core_input=batch.core_input,
        instruments=tuple(reversed(batch.instruments)),
    )
    reordered = calculate_alpha158(reordered_batch)
    np.testing.assert_array_equal(reordered.values, baseline.values[::-1])
    _, baseline_envelope = build_alpha158_raw_envelope(batch)
    _, reordered_envelope = build_alpha158_raw_envelope(reordered_batch)
    assert reordered_envelope == baseline_envelope

    first = batch.instruments[0]
    changed_close = np.array(first.research_close_index, copy=True)
    changed_close[-1] += 1.0
    changed = calculate_alpha158(
        Alpha158BatchInput(
            core_input=batch.core_input,
            instruments=(
                replace(first, research_close_index=changed_close),
                *batch.instruments[1:],
            ),
        )
    )
    assert not np.array_equal(changed.values[0], baseline.values[0], equal_nan=True)
    np.testing.assert_array_equal(changed.values[1:], baseline.values[1:])


def test_units_calendar_shape_and_cutoff_fail_closed() -> None:
    batch = synthetic_batch()
    first, second, third = batch.instruments
    with pytest.raises(Alpha158InputError, match="alpha158_volume_unit_must_be_lots"):
        replace(first, volume_unit="shares")  # type: ignore[arg-type]
    with pytest.raises(Alpha158InputError, match="alpha158_input_shape_mismatch"):
        replace(first, volume_lots=first.volume_lots[:-1])
    for invalid_dates in (
        (*first.market_dates[:-1], first.market_dates[-2]),
        tuple(reversed(first.market_dates)),
    ):
        with pytest.raises(
            Alpha158InputError,
            match="alpha158_market_dates_not_strictly_increasing",
        ):
            replace(first, market_dates=invalid_dates)
    changed_dates = (*second.market_dates[:-1], second.market_dates[-1] + timedelta(days=1))
    with pytest.raises(Alpha158InputError, match="alpha158_common_calendar_mismatch"):
        Alpha158BatchInput(
            core_input=batch.core_input,
            instruments=(first, replace(second, market_dates=changed_dates), third),
        )
    deleted_instruments = tuple(delete_date(instrument, 20) for instrument in batch.instruments)
    with pytest.raises(Alpha158InputError, match="alpha158_common_calendar_mismatch"):
        Alpha158BatchInput(
            core_input=batch.core_input,
            instruments=deleted_instruments,
        )
    future_available = (
        *first.available_at[:-1],
        batch.core_input.cutoff_at + timedelta(seconds=1),
    )
    with pytest.raises(Alpha158InputError, match="alpha158_input_after_cutoff"):
        Alpha158BatchInput(
            core_input=batch.core_input,
            instruments=(replace(first, available_at=future_available), second, third),
        )
    invalid_raw_close = np.array(first.raw_close, copy=True)
    invalid_raw_close[-1] = 0.0
    assert np.isnan(replace(first, raw_close=invalid_raw_close).qlib_inputs()[-1, 5])
    assert date(2025, 10, 1) not in common_dates()
    assert date(2025, 10, 2) not in common_dates()
    assert date(2025, 10, 3) not in common_dates()
