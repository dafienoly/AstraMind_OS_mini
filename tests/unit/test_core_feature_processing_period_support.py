"""Exact later-period processing parents shared by projection contract tests."""

from __future__ import annotations

from datetime import UTC, date, datetime, time
from typing import cast

from astramind_mini.contracts import DatasetRef, DataSnapshot
from astramind_mini.strategy_research.core.contracts import (
    CoreDatasetSlice,
    CoreInputLayer,
    CoreInputSnapshot,
    CoreUniverseDecision,
)
from astramind_mini.strategy_research.core.feature_builder import (
    build_core_raw_feature_envelope,
)
from astramind_mini.strategy_research.core.feature_processing import (
    CoreProcessedFeatureEnvelopeParents,
    CoreProcessedFeaturePanelParents,
    CoreProcessingControlRow,
    build_core_processing_control_panel,
)
from astramind_mini.strategy_research.core.feature_selection import (
    load_core_selection_prior_manifest,
)
from astramind_mini.strategy_research.core.feature_values import (
    CoreRawFeatureRowDraft,
    FeatureAvailabilityState,
)
from astramind_mini.strategy_research.core.identity import freeze_core_input_snapshot
from astramind_mini.strategy_research.core.packages import (
    ASTRAMIND_F0,
    CORE_FEATURE_ORDERS,
    FORMULAIC_ALPHA101,
    QLIB_ALPHA158,
)
from astramind_mini.strategy_research.core.universe import core_universe_content_hash

HASH_A = "sha256:" + "a" * 64
HASH_B = "sha256:" + "b" * 64
INSTRUMENTS = ("A", "B", "C")
PACKAGES = {
    item.package_id: item
    for item in (
        ASTRAMIND_F0,
        QLIB_ALPHA158,
        FORMULAIC_ALPHA101,
    )
}


def exact_period_panel_parents(
    package_id: str,
    days: tuple[date, ...] = (date(2026, 1, 5), date(2026, 1, 6)),
    instruments: tuple[str, ...] = INSTRUMENTS,
    computation_manifest_hash: str | None = None,
) -> CoreProcessedFeaturePanelParents:
    return CoreProcessedFeaturePanelParents.freeze(
        tuple(
            exact_daily_parents(
                package_id,
                day,
                instruments,
                computation_manifest_hash,
            )
            for day in days
        )
    )


def exact_daily_parents(
    package_id: str,
    day: date,
    instruments: tuple[str, ...] = INSTRUMENTS,
    computation_manifest_hash: str | None = None,
) -> CoreProcessedFeatureEnvelopeParents:
    cutoff = datetime.combine(day, time(18), tzinfo=UTC)
    decisions = _universe(day, cutoff, instruments)
    universe_hash = core_universe_content_hash(decisions)
    core_input = _core_input(day, cutoff, universe_hash, len(instruments))
    package = PACKAGES[package_id]
    feature_order = CORE_FEATURE_ORDERS[package_id]
    versions = {
        item.feature_id: item.definition_version
        for item in load_core_selection_prior_manifest().package_entries(package_id)
    }
    raw = build_core_raw_feature_envelope(
        core_input=core_input,
        package_spec=package,
        computation_manifest_hash=(computation_manifest_hash or _computation_hash(package_id)),
        calculation_sessions=core_input.common_sessions,
        feature_order=feature_order,
        rows=_raw_rows(cutoff, feature_order, versions, instruments),
    )
    control_rows = tuple(
        CoreProcessingControlRow(
            instrument_id=item.instrument_id,
            decision_date=day,
            universe_decision=item,
            sw_l1="I1",
            sw_l1_available_at=cutoff,
            float_market_cap=float((index + 1) * 1_000_000),
            float_market_cap_available_at=cutoff,
        )
        for index, item in enumerate(decisions)
    )
    controls = build_core_processing_control_panel(
        decision_date=day,
        input_cutoff=cutoff,
        universe_rows=decisions,
        rows=control_rows,
        source_dataset_bindings=(("industry_membership", HASH_B),),
    )
    return CoreProcessedFeatureEnvelopeParents.freeze(
        core_input=core_input,
        universe_rows=decisions,
        raw_envelope=raw,
        control_panel=controls,
    )


def _universe(
    day: date,
    cutoff: datetime,
    instruments: tuple[str, ...],
) -> tuple[CoreUniverseDecision, ...]:
    return tuple(
        CoreUniverseDecision(
            instrument_id=instrument,
            decision_date=day,
            input_cutoff=cutoff,
            universe_version="U0-v1",
            research_member=True,
            new_risk_eligible=True,
            diagnostic_pool=(),
            reason_codes=(),
            listed_common_sessions=400,
            liquidity_observation_count=20,
            median_amount_20_cny=100_000_000,
        )
        for instrument in instruments
    )


def _core_input(
    day: date,
    cutoff: datetime,
    universe_hash: str,
    row_count: int,
) -> CoreInputSnapshot:
    data_snapshot = DataSnapshot(
        snapshot_id=f"snapshot:{day.isoformat()}",
        as_of=cutoff,
        datasets=(
            DatasetRef(
                dataset_name="adjusted_market",
                dataset_version=f"daily-{day.isoformat()}",
                schema_version="1.0.0",
                content_hash=HASH_A,
            ),
        ),
        known_gaps=(),
        created_at=cutoff,
        code_identity="period-projection-fixture-v1",
    )
    dataset = CoreDatasetSlice(
        dataset_name="adjusted_market",
        dataset_version=f"daily-{day.isoformat()}",
        schema_version="1.0.0",
        content_hash=HASH_A,
        row_count=row_count,
        min_market_date=day,
        max_market_date=day,
        max_available_at=cutoff,
        input_layer=CoreInputLayer.COMPLETED_DAILY,
        sealed=True,
    )
    return freeze_core_input_snapshot(
        data_snapshot=data_snapshot,
        decision_date=day,
        cutoff_at=cutoff,
        common_calendar_id="period-fixture-calendar-v1",
        common_sessions=(day,),
        universe_content_hash=universe_hash,
        datasets=(dataset,),
    )


def _raw_rows(
    cutoff: datetime,
    feature_order: tuple[str, ...],
    versions: dict[str, str],
    instruments: tuple[str, ...],
) -> tuple[CoreRawFeatureRowDraft, ...]:
    return tuple(
        _raw_row(
            instrument=instrument,
            instrument_index=instrument_index,
            feature=feature,
            feature_index=feature_index,
            version=versions[feature],
            cutoff=cutoff,
        )
        for instrument_index, instrument in enumerate(instruments)
        for feature_index, feature in enumerate(feature_order)
    )


def _raw_row(
    *,
    instrument: str,
    instrument_index: int,
    feature: str,
    feature_index: int,
    version: str,
    cutoff: datetime,
) -> CoreRawFeatureRowDraft:
    exceptional = feature_index == 0 and instrument_index in {1, 2}
    state = (
        FeatureAvailabilityState.MISSING
        if exceptional and instrument_index == 1
        else (
            FeatureAvailabilityState.NOT_APPLICABLE
            if exceptional
            else FeatureAvailabilityState.OBSERVED
        )
    )
    return CoreRawFeatureRowDraft(
        instrument_id=instrument,
        decision_time=cutoff,
        feature_definition_id=feature,
        feature_definition_version=version,
        value_raw=(
            None
            if state != FeatureAvailabilityState.OBSERVED
            else float((instrument_index + 1) * (feature_index + 1))
        ),
        availability_state=state,
        missing_reason_code=None if state == FeatureAvailabilityState.OBSERVED else "fixture_gap",
    )


def _computation_hash(package_id: str) -> str:
    binding = load_core_selection_prior_manifest().package_bindings[package_id]
    return cast(str, binding["computation_manifest_hash"])


__all__ = ["INSTRUMENTS", "PACKAGES", "exact_daily_parents", "exact_period_panel_parents"]
