"""Core feature-value states shared by raw and processed feature views."""

from __future__ import annotations

import math
from enum import StrEnum
from typing import Literal

from pydantic import model_validator

from astramind_mini.contracts.base import (
    AwareDatetime,
    ContractModel,
    Identifier,
    Version,
)


class FeatureAvailabilityState(StrEnum):
    OBSERVED = "observed"
    MISSING = "missing"
    NOT_APPLICABLE = "not_applicable"


class CoreImputationSource(StrEnum):
    NONE = "none"
    SW_L1_MEDIAN = "sw_l1_median"
    U0_MEDIAN = "u0_median"


class CoreRawFeatureRowDraft(ContractModel):
    """Formula output before a FeatureSnapshot identity exists."""

    instrument_id: Identifier
    decision_time: AwareDatetime
    feature_definition_id: Identifier
    feature_definition_version: Version
    value_raw: float | None = None
    availability_state: FeatureAvailabilityState
    missing_reason_code: Identifier | None = None

    @model_validator(mode="after")
    def validate_raw_state(self) -> CoreRawFeatureRowDraft:
        _validate_raw_state(
            state=self.availability_state,
            value_raw=self.value_raw,
            missing_reason_code=self.missing_reason_code,
        )
        return self


class CoreFeatureValue(ContractModel):
    feature_snapshot_id: Identifier
    instrument_id: Identifier
    decision_time: AwareDatetime
    feature_definition_id: Identifier
    feature_definition_version: Version
    value_raw: float | None = None
    availability_state: FeatureAvailabilityState
    missing_reason_code: Identifier | None = None
    value_winsorized: float | None = None
    value_standardized: float | None = None
    imputation_source: CoreImputationSource
    missing_indicator: bool
    not_applicable_indicator: bool
    neutralized_diagnostic: float | None = None
    data_semantics_version: Literal["core-data-semantics-v1"]

    @model_validator(mode="after")
    def validate_state_and_processing(self) -> CoreFeatureValue:
        _validate_raw_state(
            state=self.availability_state,
            value_raw=self.value_raw,
            missing_reason_code=self.missing_reason_code,
        )
        expected_missing = self.availability_state == FeatureAvailabilityState.MISSING
        expected_na = self.availability_state == FeatureAvailabilityState.NOT_APPLICABLE
        if self.missing_indicator != expected_missing:
            raise ValueError("missing_indicator must match availability_state")
        if self.not_applicable_indicator != expected_na:
            raise ValueError("not_applicable_indicator must match availability_state")
        _validate_imputation(self)
        _validate_processed_values(self)
        return self


def _validate_raw_state(
    *,
    state: FeatureAvailabilityState,
    value_raw: float | None,
    missing_reason_code: str | None,
) -> None:
    if state == FeatureAvailabilityState.OBSERVED:
        if value_raw is None or not math.isfinite(value_raw):
            raise ValueError("observed state requires a finite raw value")
        if missing_reason_code is not None:
            raise ValueError("observed state cannot carry a missing reason")
        return
    if value_raw is not None:
        raise ValueError("missing and not-applicable states cannot carry a raw value")
    if missing_reason_code is None:
        raise ValueError("missing and not-applicable states require a stable reason code")


def _validate_imputation(value: CoreFeatureValue) -> None:
    if value.availability_state == FeatureAvailabilityState.OBSERVED:
        if value.imputation_source != CoreImputationSource.NONE:
            raise ValueError("observed values cannot be imputed")
    elif (
        value.availability_state == FeatureAvailabilityState.NOT_APPLICABLE
        and value.imputation_source == CoreImputationSource.SW_L1_MEDIAN
    ):
        raise ValueError("not-applicable values cannot use an industry median")


def _validate_processed_values(value: CoreFeatureValue) -> None:
    processed = (value.value_winsorized, value.value_standardized)
    if (processed[0] is None) != (processed[1] is None):
        raise ValueError("winsorized and standardized values must be populated together")
    if any(item is not None and not math.isfinite(item) for item in processed):
        raise ValueError("processed feature values must be finite")
    if (
        value.neutralized_diagnostic is not None
        and not math.isfinite(value.neutralized_diagnostic)
    ):
        raise ValueError("neutralized diagnostics must be finite")
    if value.neutralized_diagnostic is not None and value.value_standardized is None:
        raise ValueError("neutralized diagnostics require a standardized value")
    if value.imputation_source != CoreImputationSource.NONE and processed[0] is None:
        raise ValueError("an imputed model view requires processed numeric values")
    if (
        value.availability_state != FeatureAvailabilityState.OBSERVED
        and value.imputation_source == CoreImputationSource.NONE
        and processed[0] is not None
    ):
        raise ValueError("processed non-observed values must record their imputation source")


__all__ = [
    "CoreFeatureValue",
    "CoreImputationSource",
    "CoreRawFeatureRowDraft",
    "FeatureAvailabilityState",
]
