"""Deterministic development-fold identities used only by feature selection."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime

from pydantic import Field, model_validator

from astramind_mini.contracts.base import (
    AwareDatetime,
    ContentHash,
    ContractModel,
    Identifier,
)

from ...application.identity import research_hash


class CoreSelectionSubfold(ContractModel):
    subfold_id: Identifier
    decision_dates: tuple[date, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_dates(self) -> CoreSelectionSubfold:
        if self.decision_dates != tuple(sorted(set(self.decision_dates))):
            raise ValueError("selection subfold dates must be unique and ordered")
        return self


class CoreSelectionFold(ContractModel):
    fold_id: Identifier
    content_hash: ContentHash
    decision_dates: tuple[date, ...] = Field(min_length=1)
    label_maturity_cutoff: AwareDatetime
    subfolds: tuple[CoreSelectionSubfold, CoreSelectionSubfold, CoreSelectionSubfold]

    @model_validator(mode="after")
    def validate_identity(self) -> CoreSelectionFold:
        if self.decision_dates != tuple(sorted(set(self.decision_dates))):
            raise ValueError("selection fold dates must be unique and ordered")
        flattened = tuple(day for subfold in self.subfolds for day in subfold.decision_dates)
        if flattened != self.decision_dates:
            raise ValueError("three continuous subfolds must exactly partition the fold")
        expected_hash = research_hash(
            {
                "schema": "core-selection-fold-v1",
                "decision_dates": self.decision_dates,
                "label_maturity_cutoff": self.label_maturity_cutoff,
                "subfolds": self.subfolds,
            }
        )
        expected_id = f"core-selection-fold:{expected_hash.removeprefix('sha256:')}"
        if self.content_hash != expected_hash or self.fold_id != expected_id:
            raise ValueError("selection fold canonical identity mismatch")
        return self


class CoreSelectionPlan(ContractModel):
    plan_id: Identifier
    content_hash: ContentHash
    folds: tuple[CoreSelectionFold, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_identity(self) -> CoreSelectionPlan:
        if len({item.fold_id for item in self.folds}) != len(self.folds):
            raise ValueError("selection plan folds must be unique")
        expected_hash = research_hash({"schema": "core-selection-plan-v1", "folds": self.folds})
        expected_id = f"core-selection-plan:{expected_hash.removeprefix('sha256:')}"
        if self.content_hash != expected_hash or self.plan_id != expected_id:
            raise ValueError("selection plan canonical identity mismatch")
        return self


def freeze_core_selection_fold(
    *,
    decision_dates: Sequence[date],
    label_maturity_cutoff: datetime,
    subfold_dates: Sequence[Sequence[date]],
) -> CoreSelectionFold:
    if len(subfold_dates) != 3:
        raise ValueError("selection fold requires exactly three continuous subfolds")
    dates = tuple(decision_dates)
    subfolds = tuple(
        CoreSelectionSubfold(
            subfold_id=f"subfold-{index + 1}",
            decision_dates=tuple(days),
        )
        for index, days in enumerate(subfold_dates)
    )
    payload = {
        "schema": "core-selection-fold-v1",
        "decision_dates": dates,
        "label_maturity_cutoff": label_maturity_cutoff,
        "subfolds": subfolds,
    }
    content_hash = research_hash(payload)
    return CoreSelectionFold(
        fold_id=f"core-selection-fold:{content_hash.removeprefix('sha256:')}",
        content_hash=content_hash,
        decision_dates=dates,
        label_maturity_cutoff=label_maturity_cutoff,
        subfolds=subfolds,  # type: ignore[arg-type]
    )


def freeze_core_selection_plan(
    folds: Sequence[CoreSelectionFold],
) -> CoreSelectionPlan:
    frozen = tuple(folds)
    content_hash = research_hash({"schema": "core-selection-plan-v1", "folds": frozen})
    return CoreSelectionPlan(
        plan_id=f"core-selection-plan:{content_hash.removeprefix('sha256:')}",
        content_hash=content_hash,
        folds=frozen,
    )


__all__ = [
    "CoreSelectionFold",
    "CoreSelectionPlan",
    "CoreSelectionSubfold",
    "freeze_core_selection_fold",
    "freeze_core_selection_plan",
]
