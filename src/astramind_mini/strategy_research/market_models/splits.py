"""Deterministic label-mature walk-forward splits."""

from __future__ import annotations

from calendar import monthrange
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime

from ..application.identity import research_hash
from .recipes import MarketModelRecipe
from .samples import (
    EvidencePurpose,
    MembershipKnowledge,
    PointInTimeSample,
    sample_is_eligible,
)


@dataclass(frozen=True)
class WalkForwardFold:
    fold_id: str
    validation_month: date
    train_start: datetime
    train_end: datetime
    maturity_cutoff: datetime
    train_sample_ids: tuple[str, ...]
    validation_sample_ids: tuple[str, ...]


def build_walk_forward_folds(
    samples: Sequence[PointInTimeSample],
    *,
    recipe: MarketModelRecipe,
    purpose: EvidencePurpose,
    evidence_cutoff: datetime,
) -> tuple[WalkForwardFold, ...]:
    membership_eligible = tuple(
        sample
        for sample in samples
        if _membership_is_allowed(sample.membership_knowledge, purpose=purpose)
    )
    months = _complete_validation_months(
        membership_eligible,
        evidence_cutoff=evidence_cutoff,
        limit=recipe.validation_months,
    )
    return tuple(
        _build_fold(
            membership_eligible,
            recipe=recipe,
            validation_month=date(year, month, 1),
            evidence_cutoff=evidence_cutoff,
        )
        for year, month in months
    )


def _complete_validation_months(
    samples: Sequence[PointInTimeSample],
    *,
    evidence_cutoff: datetime,
    limit: int,
) -> tuple[tuple[int, int], ...]:
    by_month: dict[tuple[int, int], list[PointInTimeSample]] = {}
    for sample in samples:
        month = (sample.feature_at.year, sample.feature_at.month)
        by_month.setdefault(month, []).append(sample)
    complete = sorted(
        month
        for month, candidates in by_month.items()
        if max(sample.label_available_at for sample in candidates) <= evidence_cutoff
    )
    return tuple(complete[-limit:])


def _membership_is_allowed(
    knowledge: MembershipKnowledge,
    *,
    purpose: EvidencePurpose,
) -> bool:
    return not (
        knowledge == "reconstructed_not_then_known"
        and purpose in {"sealed_replay", "audit", "prospective"}
    )


def final_training_sample_ids(
    samples: Sequence[PointInTimeSample],
    *,
    recipe: MarketModelRecipe,
    purpose: EvidencePurpose,
    training_at: datetime,
) -> tuple[str, ...]:
    training_start = _years_before(training_at, recipe.rolling_years)
    return tuple(
        sorted(
            sample.sample_id
            for sample in samples
            if training_start <= sample.feature_at <= training_at
            and sample_is_eligible(
                sample,
                purpose=purpose,
                evidence_cutoff=training_at,
            )
        )
    )


def _build_fold(
    samples: Sequence[PointInTimeSample],
    *,
    recipe: MarketModelRecipe,
    validation_month: date,
    evidence_cutoff: datetime,
) -> WalkForwardFold:
    validation_start = datetime(
        validation_month.year,
        validation_month.month,
        1,
        tzinfo=UTC,
    )
    last_day = monthrange(validation_month.year, validation_month.month)[1]
    validation_end = datetime(
        validation_month.year,
        validation_month.month,
        last_day,
        23,
        59,
        59,
        tzinfo=UTC,
    )
    train_end = validation_start
    train_start = _years_before(train_end, recipe.rolling_years)
    train_ids = tuple(
        sorted(
            sample.sample_id
            for sample in samples
            if train_start <= sample.feature_at < train_end
            and sample.label_available_at < train_end
        )
    )
    validation_ids = tuple(
        sorted(
            sample.sample_id
            for sample in samples
            if validation_start <= sample.feature_at <= validation_end
            and sample.label_available_at <= evidence_cutoff
        )
    )
    identity = {
        "family": recipe.family,
        "validation_month": validation_month,
        "train_start": train_start,
        "train_end": train_end,
        "maturity_cutoff": evidence_cutoff,
        "train_sample_ids": train_ids,
        "validation_sample_ids": validation_ids,
    }
    return WalkForwardFold(
        fold_id="market-model-fold:" + research_hash(identity).removeprefix("sha256:"),
        validation_month=validation_month,
        train_start=train_start,
        train_end=train_end,
        maturity_cutoff=evidence_cutoff,
        train_sample_ids=train_ids,
        validation_sample_ids=validation_ids,
    )


def _years_before(value: datetime, years: int) -> datetime:
    try:
        return value.replace(year=value.year - years)
    except ValueError:
        return value.replace(year=value.year - years, day=28)


__all__ = ["WalkForwardFold", "build_walk_forward_folds", "final_training_sample_ids"]
