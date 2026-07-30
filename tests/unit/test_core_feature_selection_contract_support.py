"""Validated envelope, label, and panel builders for production selection tests."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, time
from pathlib import Path

from test_core_feature_selection_profile_support import (
    INSTRUMENTS,
    cross_section,
    feature_rows,
)

from astramind_mini.strategy_research.application.identity import research_hash
from astramind_mini.strategy_research.core.calendar import freeze_core_common_calendar
from astramind_mini.strategy_research.core.contracts import CoreUniverseDecision
from astramind_mini.strategy_research.core.feature_processing import (
    CoreCrossSectionStatus,
    CoreProcessedFeatureEnvelope,
    CoreProcessedFeaturePanelEntry,
    CoreProcessedFeaturePanelManifest,
    CoreProcessingSpec,
)
from astramind_mini.strategy_research.core.feature_selection import (
    CoreSelectionPriorEntry,
    load_core_selection_prior_manifest,
)
from astramind_mini.strategy_research.core.labels import (
    CoreForwardPriceObservation,
    CoreForwardReturnLabelBatch,
    CoreForwardReturnLabelSpec,
    CoreLabelHorizon,
    build_core_forward_return_label_batch,
)
from astramind_mini.strategy_research.core.universe import core_universe_content_hash

_CALENDAR_FIXTURE = Path(__file__).parents[1] / "fixtures" / "core" / "f0" / "golden_case.json"
_SESSIONS = tuple(
    date.fromisoformat(item)
    for item in json.loads(_CALENDAR_FIXTURE.read_text(encoding="utf-8"))["common_sessions"]
)
CALENDAR = freeze_core_common_calendar(
    calendar_id="fixture-stage-s-common-calendar-v1",
    sessions=_SESSIONS,
)
SNAPSHOT_AS_OF = datetime.combine(CALENDAR.sessions[-1], time(17), tzinfo=UTC)


def fixture_universe(day: date) -> tuple[CoreUniverseDecision, ...]:
    return tuple(
        CoreUniverseDecision(
            instrument_id=instrument,
            decision_date=day,
            input_cutoff=datetime.combine(day, time(16), tzinfo=UTC),
            universe_version="U0-v1",
            research_member=True,
            new_risk_eligible=True,
            diagnostic_pool=(),
            reason_codes=(),
            listed_common_sessions=400,
            liquidity_observation_count=20,
            median_amount_20_cny=100_000_000,
        )
        for instrument in INSTRUMENTS
    )


def fixture_envelope(
    *,
    package_id: str,
    prior_entries: tuple[CoreSelectionPriorEntry, ...],
    decisions: tuple[CoreUniverseDecision, ...],
    index: int,
    profile: str,
    horizon: CoreLabelHorizon,
) -> CoreProcessedFeatureEnvelope:
    prior = load_core_selection_prior_manifest()
    binding = prior.package_bindings[package_id]
    feature_order = tuple(item.feature_id for item in prior_entries)
    versions = {item.feature_id: item.definition_version for item in prior_entries}
    directions = {item.feature_id: item.expected_direction for item in prior_entries}
    rows_by_feature = {
        feature_id: feature_rows(
            feature_id=feature_id,
            version=versions[feature_id],
            direction=directions[feature_id],
            feature_index=feature_index,
            day_index=index,
            profile=profile,
            horizon=horizon,
        )
        for feature_index, feature_id in enumerate(feature_order)
    }
    rows = tuple(
        row
        for instrument in INSTRUMENTS
        for feature_id in feature_order
        for row in rows_by_feature[feature_id]
        if row.instrument_id == instrument
    )
    cross_sections = tuple(
        cross_section(
            feature_id,
            versions[feature_id],
            rows_by_feature[feature_id],
        )
        for feature_id in feature_order
    )
    payload = _envelope_payload(
        package_id=package_id,
        decisions=decisions,
        index=index,
        binding=binding,
        feature_order=feature_order,
        rows=rows,
        cross_sections=cross_sections,
    )
    content_hash = research_hash(payload)
    return CoreProcessedFeatureEnvelope.model_validate(
        {
            "envelope_id": f"core-processed:{content_hash.removeprefix('sha256:')}",
            "content_hash": content_hash,
            **{key: value for key, value in payload.items() if key != "schema"},
        }
    )


def _envelope_payload(
    *,
    package_id: str,
    decisions: tuple[CoreUniverseDecision, ...],
    index: int,
    binding: dict[str, object],
    feature_order: tuple[str, ...],
    rows: tuple[object, ...],
    cross_sections: tuple[object, ...],
) -> dict[str, object]:
    spec = CoreProcessingSpec()
    return {
        "schema": "core-processed-feature-envelope-v1",
        "decision_date": decisions[0].decision_date,
        "core_input_snapshot_id": f"fixture-input-{package_id}-{index}",
        "core_input_content_hash": research_hash({"input": (package_id, index)}),
        "raw_feature_snapshot_id": f"fixture-raw-{package_id}-{index}",
        "raw_feature_content_hash": research_hash({"raw": (package_id, index)}),
        "raw_manifest_id": f"fixture-raw-manifest-{package_id}",
        "raw_manifest_content_hash": research_hash({"manifest": package_id}),
        "package_id": package_id,
        "definition_registry_hash": binding["required_definition_registry_hash"],
        "computation_manifest_hash": binding["computation_manifest_hash"],
        "universe_content_hash": core_universe_content_hash(decisions),
        "control_panel_id": f"fixture-control-{package_id}-{index}",
        "control_panel_content_hash": research_hash({"control": (package_id, index)}),
        "processing_spec": spec,
        "processing_spec_hash": research_hash(spec),
        "feature_order": feature_order,
        "instrument_order": INSTRUMENTS,
        "rows": rows,
        "cross_sections": cross_sections,
        "blocked_feature_ids": tuple(
            item.feature_id
            for item in cross_sections
            if item.status == CoreCrossSectionStatus.NO_OBSERVED
        ),
    }


def fixture_label_batch(
    *,
    day: date,
    decisions: tuple[CoreUniverseDecision, ...],
    horizon: CoreLabelHorizon,
    index: int,
) -> CoreForwardReturnLabelBatch:
    entry = CALENDAR.sessions[CALENDAR.sessions.index(day) + 1]
    terminal = CALENDAR.sessions[CALENDAR.sessions.index(day) + horizon.sessions]
    prices = tuple(
        observation
        for position, instrument in enumerate(INSTRUMENTS)
        for observation in (
            CoreForwardPriceObservation(
                instrument_id=instrument,
                trade_date=entry,
                research_open=100.0,
                research_close=100.0,
                available_at=SNAPSHOT_AS_OF,
                source_record_hash=research_hash({"entry": (horizon, index, instrument)}),
            ),
            CoreForwardPriceObservation(
                instrument_id=instrument,
                trade_date=terminal,
                research_open=100.0,
                research_close=101.0 + position,
                available_at=SNAPSHOT_AS_OF,
                source_record_hash=research_hash({"terminal": (horizon, index, instrument)}),
            ),
        )
    )
    return build_core_forward_return_label_batch(
        spec=CoreForwardReturnLabelSpec(horizon=horizon),
        decision_date=day,
        common_calendar=CALENDAR,
        universe_rows=decisions,
        prices=prices,
        label_data_snapshot_id=f"fixture-label-snapshot-{horizon}-{index}",
        label_data_snapshot_content_hash=research_hash(
            {"label-snapshot": (horizon, index)}
        ),
        label_data_snapshot_as_of=SNAPSHOT_AS_OF,
        label_available_cutoff=SNAPSHOT_AS_OF,
    )


def fixture_panel(
    envelopes: tuple[CoreProcessedFeatureEnvelope, ...],
) -> CoreProcessedFeaturePanelManifest:
    entries = tuple(
        CoreProcessedFeaturePanelEntry(
            decision_date=item.decision_date,
            core_input_snapshot_id=item.core_input_snapshot_id,
            core_input_content_hash=item.core_input_content_hash,
            raw_envelope_id=item.raw_feature_snapshot_id,
            raw_envelope_content_hash=item.raw_feature_content_hash,
            processed_envelope_id=item.envelope_id,
            processed_envelope_content_hash=item.content_hash,
            universe_content_hash=item.universe_content_hash,
            control_panel_id=item.control_panel_id,
            control_panel_content_hash=item.control_panel_content_hash,
        )
        for item in envelopes
    )
    payload = {
        "schema": "core-processed-feature-panel-v1",
        "package_id": envelopes[0].package_id,
        "feature_order": envelopes[0].feature_order,
        "entries": entries,
    }
    content_hash = research_hash(payload)
    return CoreProcessedFeaturePanelManifest(
        panel_manifest_id=f"core-processed-panel:{content_hash.removeprefix('sha256:')}",
        content_hash=content_hash,
        package_id=envelopes[0].package_id,
        feature_order=envelopes[0].feature_order,
        entries=entries,
    )


__all__ = [
    "CALENDAR",
    "INSTRUMENTS",
    "SNAPSHOT_AS_OF",
    "fixture_envelope",
    "fixture_label_batch",
    "fixture_panel",
    "fixture_universe",
]
