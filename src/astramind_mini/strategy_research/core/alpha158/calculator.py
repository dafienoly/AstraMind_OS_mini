"""Deterministic NumPy implementation of the frozen Qlib Alpha158 package."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime

import numpy as np
import numpy.typing as npt

from ..feature_builder import build_core_raw_feature_envelope
from ..feature_output import CoreRawFeatureEnvelope
from ..feature_values import CoreRawFeatureRowDraft, FeatureAvailabilityState
from ..packages import QLIB_ALPHA158
from .definitions import (
    ALPHA158_MANIFEST,
    DEFINITION_VERSION,
    PAIRS_SHA256,
    QLIB_ALPHA158_NAMES,
    WINDOWS,
    alpha158_computation_manifest_hash,
    validate_frozen_manifest,
)
from .inputs import Alpha158BatchInput, FloatArray
from .regression import rolling_residual, rolling_rsquare, rolling_slope
from .rolling import (
    ref,
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

MaskArray = npt.NDArray[np.uint8]
FINITE = np.uint8(0)
NAN = np.uint8(1)
POSITIVE_INFINITY = np.uint8(2)
NEGATIVE_INFINITY = np.uint8(3)
MISSING_REASON = "alpha158_non_finite_formula_result"


@dataclass(frozen=True)
class Alpha158Computation:
    core_input_snapshot_id: str
    core_input_content_hash: str
    common_calendar_hash: str
    package_id: str
    data_semantics_version: str
    instrument_ids: tuple[str, ...]
    market_dates: tuple[date, ...]
    feature_names: tuple[str, ...]
    manifest_pairs_sha256: str
    computation_manifest_hash: str
    input_sha256: str
    values_sha256: str
    nonfinite_mask_sha256: str
    content_hash: str
    values: FloatArray
    nonfinite_mask: MaskArray


def calculate_alpha158(batch: Alpha158BatchInput) -> Alpha158Computation:
    validate_frozen_manifest()
    batch.validated_sessions()
    inputs = batch.qlib_input_cube()
    values = np.stack(tuple(_calculate_instrument(item) for item in inputs))
    return _freeze_computation(batch, inputs=inputs, values=values)


def calculate_alpha158_in_chunks(
    batch: Alpha158BatchInput,
    *,
    chunk_size: int,
) -> Alpha158Computation:
    if chunk_size <= 0:
        raise ValueError("alpha158_chunk_size_must_be_positive")
    validate_frozen_manifest()
    batch.validated_sessions()
    inputs = batch.qlib_input_cube()
    chunks = tuple(
        np.stack(
            tuple(
                _calculate_instrument(inputs[index])
                for index in range(start, min(start + chunk_size, len(inputs)))
            )
        )
        for start in range(0, len(inputs), chunk_size)
    )
    return _freeze_computation(
        batch,
        inputs=inputs,
        values=np.concatenate(chunks, axis=0),
    )


def _freeze_computation(
    batch: Alpha158BatchInput,
    *,
    inputs: FloatArray,
    values: FloatArray,
) -> Alpha158Computation:
    values = _readonly_float64(values)
    mask = _readonly_mask(_nonfinite_mask(values))
    input_hash = _array_sha256(inputs)
    values_hash = _array_sha256(values)
    mask_hash = hashlib.sha256(mask.tobytes(order="C")).hexdigest()
    computation_manifest_hash = alpha158_computation_manifest_hash()
    identity = {
        "core_input_snapshot_id": batch.core_input.core_input_snapshot_id,
        "core_input_content_hash": batch.core_input.content_hash,
        "common_calendar_hash": batch.core_input.common_calendar_hash,
        "package_id": ALPHA158_MANIFEST.package_id,
        "data_semantics_version": ALPHA158_MANIFEST.data_semantics_version,
        "instrument_ids": batch.instrument_ids,
        "market_dates": tuple(day.isoformat() for day in batch.market_dates),
        "feature_names": QLIB_ALPHA158_NAMES,
        "manifest_pairs_sha256": PAIRS_SHA256,
        "computation_manifest_hash": computation_manifest_hash,
        "input_sha256": input_hash,
        "values_sha256": values_hash,
        "nonfinite_mask_sha256": mask_hash,
    }
    content_hash = "sha256:" + hashlib.sha256(_canonical_json(identity)).hexdigest()
    return Alpha158Computation(
        core_input_snapshot_id=batch.core_input.core_input_snapshot_id,
        core_input_content_hash=batch.core_input.content_hash,
        common_calendar_hash=batch.core_input.common_calendar_hash,
        package_id=ALPHA158_MANIFEST.package_id,
        data_semantics_version=ALPHA158_MANIFEST.data_semantics_version,
        instrument_ids=batch.instrument_ids,
        market_dates=batch.market_dates,
        feature_names=QLIB_ALPHA158_NAMES,
        manifest_pairs_sha256=PAIRS_SHA256,
        computation_manifest_hash=computation_manifest_hash,
        input_sha256=input_hash,
        values_sha256=values_hash,
        nonfinite_mask_sha256=mask_hash,
        content_hash=content_hash,
        values=values,
        nonfinite_mask=mask,
    )


def build_alpha158_raw_envelope(
    batch: Alpha158BatchInput,
) -> tuple[Alpha158Computation, CoreRawFeatureEnvelope]:
    result = calculate_alpha158(batch)
    if result.market_dates[-1] != batch.core_input.decision_date:
        raise ValueError("alpha158_decision_date_missing_from_common_calendar")
    rows = tuple(
        _raw_row(
            instrument_id=instrument_id,
            feature_id=feature_id,
            value=float(result.values[instrument_index, -1, feature_index]),
            decision_time=batch.core_input.cutoff_at,
        )
        for instrument_index, instrument_id in enumerate(result.instrument_ids)
        for feature_index, feature_id in enumerate(result.feature_names)
    )
    envelope = build_core_raw_feature_envelope(
        core_input=batch.core_input,
        package_spec=QLIB_ALPHA158,
        computation_manifest_hash=result.computation_manifest_hash,
        calculation_sessions=result.market_dates,
        feature_order=result.feature_names,
        rows=rows,
    )
    return result, envelope


def _calculate_instrument(inputs: FloatArray) -> FloatArray:
    open_, high, low, close, volume, vwap = (inputs[:, index] for index in range(6))
    with np.errstate(all="ignore"):
        prefix = (
            (close - open_) / open_,
            (high - low) / open_,
            (close - open_) / (high - low + 1e-12),
            (high - np.maximum(open_, close)) / open_,
            (high - np.maximum(open_, close)) / (high - low + 1e-12),
            (np.minimum(open_, close) - low) / open_,
            (np.minimum(open_, close) - low) / (high - low + 1e-12),
            (2.0 * close - high - low) / open_,
            (2.0 * close - high - low) / (high - low + 1e-12),
            open_ / close,
            high / close,
            low / close,
            vwap / close,
        )
        families = tuple(_rolling_families(close, high, low, volume, window) for window in WINDOWS)
    columns = prefix + tuple(
        family[family_index] for family_index in range(29) for family in families
    )
    return np.column_stack(columns)


def _rolling_families(
    close: FloatArray,
    high: FloatArray,
    low: FloatArray,
    volume: FloatArray,
    window: int,
) -> tuple[FloatArray, ...]:
    close_ref = ref(close, 1)
    volume_ref = ref(volume, 1)
    close_delta = close - close_ref
    volume_delta = volume - volume_ref
    close_abs = np.abs(close_delta)
    volume_abs = np.abs(volume_delta)
    close_ratio = close / close_ref
    volume_log = np.log(volume + 1.0)
    volume_ratio_log = np.log(volume / volume_ref + 1.0)
    positive_close = np.maximum(close_delta, 0.0)
    negative_close = np.maximum(-close_delta, 0.0)
    positive_volume = np.maximum(volume_delta, 0.0)
    negative_volume = np.maximum(-volume_delta, 0.0)
    high_max = rolling_max(high, window)
    low_min = rolling_min(low, window)
    close_abs_volume = np.abs(close_ratio - 1.0) * volume
    close_abs_sum = rolling_sum(close_abs, window)
    volume_abs_sum = rolling_sum(volume_abs, window)
    positive_close_sum = rolling_sum(positive_close, window)
    negative_close_sum = rolling_sum(negative_close, window)
    positive_volume_sum = rolling_sum(positive_volume, window)
    negative_volume_sum = rolling_sum(negative_volume, window)
    count_positive = rolling_mean((close > close_ref).astype(np.float64), window)
    count_negative = rolling_mean((close < close_ref).astype(np.float64), window)
    return (
        ref(close, window) / close,
        rolling_mean(close, window) / close,
        rolling_std(close, window) / close,
        rolling_slope(close, window) / close,
        _qlib_rsquare(close, window),
        rolling_residual(close, window) / close,
        high_max / close,
        low_min / close,
        rolling_quantile(close, window, 0.8) / close,
        rolling_quantile(close, window, 0.2) / close,
        rolling_rank(close, window),
        (close - low_min) / (high_max - low_min + 1e-12),
        rolling_idxmax(high, window) / window,
        rolling_idxmin(low, window) / window,
        (rolling_idxmax(high, window) - rolling_idxmin(low, window)) / window,
        rolling_corr(close, volume_log, window),
        rolling_corr(close_ratio, volume_ratio_log, window),
        count_positive,
        count_negative,
        count_positive - count_negative,
        positive_close_sum / (close_abs_sum + 1e-12),
        negative_close_sum / (close_abs_sum + 1e-12),
        (positive_close_sum - negative_close_sum) / (close_abs_sum + 1e-12),
        rolling_mean(volume, window) / (volume + 1e-12),
        rolling_std(volume, window) / (volume + 1e-12),
        rolling_std(close_abs_volume, window) / (rolling_mean(close_abs_volume, window) + 1e-12),
        positive_volume_sum / (volume_abs_sum + 1e-12),
        negative_volume_sum / (volume_abs_sum + 1e-12),
        (positive_volume_sum - negative_volume_sum) / (volume_abs_sum + 1e-12),
    )


def _qlib_rsquare(values: FloatArray, window: int) -> FloatArray:
    result = rolling_rsquare(values, window)
    result[np.isclose(rolling_std(values, window), 0.0, atol=2e-5)] = np.nan
    return result


def _raw_row(
    *,
    instrument_id: str,
    feature_id: str,
    value: float,
    decision_time: datetime,
) -> CoreRawFeatureRowDraft:
    if np.isfinite(value):
        return CoreRawFeatureRowDraft(
            instrument_id=instrument_id,
            decision_time=decision_time,
            feature_definition_id=feature_id,
            feature_definition_version=DEFINITION_VERSION,
            value_raw=value,
            availability_state=FeatureAvailabilityState.OBSERVED,
        )
    return CoreRawFeatureRowDraft(
        instrument_id=instrument_id,
        decision_time=decision_time,
        feature_definition_id=feature_id,
        feature_definition_version=DEFINITION_VERSION,
        value_raw=None,
        availability_state=FeatureAvailabilityState.MISSING,
        missing_reason_code=MISSING_REASON,
    )


def _nonfinite_mask(values: FloatArray) -> MaskArray:
    mask = np.zeros(values.shape, dtype=np.uint8)
    mask[np.isnan(values)] = NAN
    mask[np.isposinf(values)] = POSITIVE_INFINITY
    mask[np.isneginf(values)] = NEGATIVE_INFINITY
    return mask


def _array_sha256(values: npt.NDArray[np.generic]) -> str:
    if np.issubdtype(values.dtype, np.floating):
        canonical = np.ascontiguousarray(values, dtype="<f8").copy()
        canonical[np.isnan(canonical)] = np.float64(np.nan)
    else:
        canonical = np.ascontiguousarray(values)
    return hashlib.sha256(canonical.tobytes(order="C")).hexdigest()


def _readonly_float64(values: object) -> FloatArray:
    result = np.array(values, dtype="<f8", order="C", copy=True)
    result.setflags(write=False)
    return result


def _readonly_mask(values: object) -> MaskArray:
    result = np.array(values, dtype=np.uint8, order="C", copy=True)
    result.setflags(write=False)
    return result


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode()


__all__ = [
    "FINITE",
    "MISSING_REASON",
    "NAN",
    "NEGATIVE_INFINITY",
    "POSITIVE_INFINITY",
    "Alpha158Computation",
    "build_alpha158_raw_envelope",
    "calculate_alpha158",
    "calculate_alpha158_in_chunks",
]
