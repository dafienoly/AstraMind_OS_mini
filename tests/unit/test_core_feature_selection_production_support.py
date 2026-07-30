"""Real, fully validated Stage P/Stage S parents for selection boundary tests."""

from __future__ import annotations

from datetime import date
from functools import lru_cache

from test_core_feature_selection_contract_support import (
    CALENDAR,
    INSTRUMENTS,
    SNAPSHOT_AS_OF,
    fixture_envelope,
    fixture_label_batch,
    fixture_panel,
    fixture_universe,
)

from astramind_mini.strategy_research.core.feature_selection import (
    CoreFeatureSelectionManifest,
    CoreFeatureSelectionParents,
    CoreSelectionFold,
    freeze_core_selection_fold,
    freeze_core_selection_plan,
    load_core_selection_prior_manifest,
    rebuild_core_feature_selection,
)
from astramind_mini.strategy_research.core.labels import CoreLabelHorizon


@lru_cache(maxsize=32)
def production_selection_case(
    package_id: str,
    horizon: CoreLabelHorizon,
    *,
    profile: str = "single",
    fold_offset: int = 0,
) -> tuple[CoreFeatureSelectionParents, CoreFeatureSelectionManifest]:
    """Build valid public contracts, then invoke the sole production selector."""
    parents = production_selection_parents(
        package_id,
        horizon,
        profile=profile,
        fold_offset=fold_offset,
    )
    return parents, rebuild_core_feature_selection(parents)


@lru_cache(maxsize=32)
def production_selection_parents(
    package_id: str,
    horizon: CoreLabelHorizon,
    *,
    profile: str = "single",
    fold_offset: int = 0,
) -> CoreFeatureSelectionParents:
    prior = load_core_selection_prior_manifest()
    entries = prior.package_entries(package_id)
    dates = CALENDAR.sessions[fold_offset : fold_offset + 180]
    fold = _fold(dates)
    decisions = tuple(fixture_universe(day) for day in dates)
    absolute_indices = tuple(CALENDAR.sessions.index(day) for day in dates)
    envelopes = tuple(
        fixture_envelope(
            package_id=package_id,
            prior_entries=entries,
            decisions=day_decisions,
            index=index,
            profile=profile,
        )
        for index, day_decisions in zip(absolute_indices, decisions, strict=True)
    )
    labels = tuple(
        fixture_label_batch(
            day=day,
            decisions=day_decisions,
            horizon=horizon,
            index=index,
            profile=profile,
        )
        for index, (day, day_decisions) in zip(
            absolute_indices,
            zip(dates, decisions, strict=True),
            strict=True,
        )
    )
    return CoreFeatureSelectionParents.freeze(
        panel_manifest=fixture_panel(envelopes),
        processed_envelopes=envelopes,
        label_batches=labels,
        selection_plan=freeze_core_selection_plan((fold,)),
        selection_fold=fold,
        horizon=horizon,
        prior_manifest=prior,
    )


def _fold(dates: tuple[date, ...]) -> CoreSelectionFold:
    return freeze_core_selection_fold(
        decision_dates=dates,
        label_maturity_cutoff=SNAPSHOT_AS_OF,
        subfold_dates=(dates[:60], dates[60:120], dates[120:]),
    )


__all__ = [
    "CALENDAR",
    "INSTRUMENTS",
    "production_selection_case",
    "production_selection_parents",
]
