"""Fold-level applicable-member coverage gates."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from enum import StrEnum

from pydantic import Field, model_validator

from astramind_mini.contracts.base import ContractModel, Identifier, Version

from ..feature_processing import CoreProcessedFeatureEnvelope


class CoreCoverageReason(StrEnum):
    PASSED = "passed"
    COVERAGE_GATE_FAILED = "coverage_gate_failed"
    NO_APPLICABLE_MEMBERS = "no_applicable_members"


class CoreDailyCoverageEvidence(ContractModel):
    decision_date: date
    observed_count: int = Field(ge=0)
    applicable_count: int = Field(ge=0)
    coverage: float | None = Field(default=None, ge=0.0, le=1.0)
    passes_date_threshold: bool
    reason_code: CoreCoverageReason

    @model_validator(mode="after")
    def validate_ratio(self) -> CoreDailyCoverageEvidence:
        expected = self.observed_count / self.applicable_count if self.applicable_count else None
        if self.coverage != expected:
            raise ValueError("daily coverage ratio mismatch")
        expected_passed = expected is not None and expected >= 0.8
        expected_reason = (
            CoreCoverageReason.PASSED
            if expected_passed
            else (
                CoreCoverageReason.NO_APPLICABLE_MEMBERS
                if expected is None
                else CoreCoverageReason.COVERAGE_GATE_FAILED
            )
        )
        if self.passes_date_threshold != expected_passed or self.reason_code != expected_reason:
            raise ValueError("daily coverage threshold or reason mismatch")
        return self


class CoreFoldCoverageEvidence(ContractModel):
    feature_id: Identifier
    feature_definition_version: Version
    daily: tuple[CoreDailyCoverageEvidence, ...] = Field(min_length=1)
    qualifying_date_count: int = Field(ge=0)
    passing_date_count: int = Field(ge=0)
    passing_date_ratio: float | None = Field(default=None, ge=0.0, le=1.0)
    passed: bool
    reason_code: CoreCoverageReason

    @model_validator(mode="after")
    def validate_gate(self) -> CoreFoldCoverageEvidence:
        dates = tuple(item.decision_date for item in self.daily)
        if dates != tuple(sorted(set(dates))):
            raise ValueError("fold coverage dates must be unique and ordered")
        qualifying = sum(item.applicable_count > 0 for item in self.daily)
        passing = sum(item.passes_date_threshold for item in self.daily)
        ratio = passing / qualifying if qualifying else None
        expected_passed = ratio is not None and ratio >= 0.9
        if (
            self.qualifying_date_count != qualifying
            or self.passing_date_count != passing
            or self.passing_date_ratio != ratio
            or self.passed != expected_passed
        ):
            raise ValueError("fold coverage gate mismatch")
        expected_reason = (
            CoreCoverageReason.PASSED
            if expected_passed
            else (
                CoreCoverageReason.NO_APPLICABLE_MEMBERS
                if qualifying == 0
                else CoreCoverageReason.COVERAGE_GATE_FAILED
            )
        )
        if self.reason_code != expected_reason:
            raise ValueError("fold coverage reason mismatch")
        return self

    @property
    def mean_qualifying_coverage(self) -> float | None:
        values = [item.coverage for item in self.daily if item.coverage is not None]
        return sum(values) / len(values) if values else None


def calculate_fold_coverage(
    *,
    feature_id: str,
    envelopes: Sequence[CoreProcessedFeatureEnvelope],
) -> CoreFoldCoverageEvidence:
    """Apply the exact 80%-of-applicable on 90%-of-qualifying-dates gate."""
    daily: list[CoreDailyCoverageEvidence] = []
    version: str | None = None
    for envelope in sorted(envelopes, key=lambda item: item.decision_date):
        cross = next(
            (item for item in envelope.cross_sections if item.feature_id == feature_id),
            None,
        )
        if cross is None:
            raise ValueError("processed envelope is missing a canonical feature")
        version = cross.feature_definition_version
        if cross.applicable_count == 0:
            daily.append(
                CoreDailyCoverageEvidence(
                    decision_date=envelope.decision_date,
                    observed_count=cross.observed_count,
                    applicable_count=0,
                    coverage=None,
                    passes_date_threshold=False,
                    reason_code=CoreCoverageReason.NO_APPLICABLE_MEMBERS,
                )
            )
        else:
            passed = bool(cross.coverage is not None and cross.coverage >= 0.8)
            daily.append(
                CoreDailyCoverageEvidence(
                    decision_date=envelope.decision_date,
                    observed_count=cross.observed_count,
                    applicable_count=cross.applicable_count,
                    coverage=cross.coverage,
                    passes_date_threshold=passed,
                    reason_code=(
                        CoreCoverageReason.PASSED
                        if passed
                        else CoreCoverageReason.COVERAGE_GATE_FAILED
                    ),
                )
            )
    if version is None:
        raise ValueError("coverage requires at least one processed envelope")
    qualifying = sum(item.applicable_count > 0 for item in daily)
    passing = sum(item.passes_date_threshold for item in daily)
    ratio = passing / qualifying if qualifying else None
    passed = ratio is not None and ratio >= 0.9
    reason = (
        CoreCoverageReason.PASSED
        if passed
        else (
            CoreCoverageReason.NO_APPLICABLE_MEMBERS
            if qualifying == 0
            else CoreCoverageReason.COVERAGE_GATE_FAILED
        )
    )
    return CoreFoldCoverageEvidence(
        feature_id=feature_id,
        feature_definition_version=version,
        daily=tuple(daily),
        qualifying_date_count=qualifying,
        passing_date_count=passing,
        passing_date_ratio=ratio,
        passed=passed,
        reason_code=reason,
    )


__all__ = [
    "CoreCoverageReason",
    "CoreDailyCoverageEvidence",
    "CoreFoldCoverageEvidence",
    "calculate_fold_coverage",
]
