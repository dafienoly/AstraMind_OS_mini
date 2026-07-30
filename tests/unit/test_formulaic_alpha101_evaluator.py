from __future__ import annotations

import inspect
import json
import math
from datetime import time, timedelta
from pathlib import Path
from typing import cast

import pytest
from pydantic import ValidationError

from astramind_mini.strategy_research.core.calendar import (
    CoreCommonCalendar,
    freeze_core_common_calendar,
)
from astramind_mini.strategy_research.core.feature_output import CoreRawFeatureEnvelope
from astramind_mini.strategy_research.core.feature_values import (
    FeatureAvailabilityState,
)
from astramind_mini.strategy_research.core.formulaic_alpha101 import inputs as inputs_module
from astramind_mini.strategy_research.core.formulaic_alpha101.computation import (
    ALPHA101_COMPUTATION_MANIFEST_HASH,
)
from astramind_mini.strategy_research.core.formulaic_alpha101.evaluator import (
    Alpha101Evaluator,
    evaluate_formulaic_alpha101,
)
from astramind_mini.strategy_research.core.formulaic_alpha101.inputs import (
    Alpha101DailyObservation,
    Alpha101Panel,
)
from astramind_mini.strategy_research.core.formulaic_alpha101.reasons import (
    Alpha101Reason,
)
from astramind_mini.strategy_research.core.formulaic_alpha101.reference import (
    ScalarReferenceEvaluator,
)
from astramind_mini.strategy_research.core.formulaic_alpha101.registry import (
    ALPHA101_DEFINITIONS,
)
from astramind_mini.strategy_research.core.formulaic_alpha101.universe import (
    Alpha101UniverseHistory,
    freeze_alpha101_universe_history,
)
from astramind_mini.strategy_research.core.formulaic_alpha101.values import Alpha101Cell
from astramind_mini.strategy_research.core.packages import (
    FORMULAIC_ALPHA101,
    FORMULAIC_ALPHA101_FEATURE_ORDER,
)
from astramind_mini.strategy_research.core.semantics import IndustryMembershipObservation
from astramind_mini.strategy_research.core.universe import core_universe_content_hash
from tests.fixtures.core.formulaic_alpha101.factory import (
    EDGE_INSTRUMENTS,
    FULL_INSTRUMENTS,
    core_input,
    edge_panel,
    full_panel,
    pit_panel,
)
from tests.fixtures.core.formulaic_alpha101.golden_assertions import (
    assert_envelope_matches_golden,
    assert_evaluator_matches_golden,
)

FIXTURES = Path("tests/fixtures/core/formulaic_alpha101")


def assert_same_cell(actual: Alpha101Cell, expected: Alpha101Cell) -> None:
    assert actual.state == expected.state
    assert actual.reason == expected.reason
    if actual.value is None or expected.value is None:
        assert actual.value is expected.value
    else:
        assert math.isclose(actual.value, expected.value, rel_tol=1e-12, abs_tol=1e-12)


def fixture_manifest(name: str) -> dict[str, object]:
    return cast(
        dict[str, object],
        json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8")),
    )


def test_full_260d_matches_frozen_independent_golden_and_secondary_reference() -> None:
    panel = full_panel()
    vector = Alpha101Evaluator(panel)
    reference = ScalarReferenceEvaluator(panel)
    final_session = len(panel.sessions) - 1
    assert_evaluator_matches_golden(panel, vector, "full_260d")
    for definition in ALPHA101_DEFINITIONS:
        vector_row = vector.evaluate(definition)[final_session]
        for instrument_index, _instrument_id in enumerate(panel.instruments):
            scalar = reference.evaluate(
                definition,
                session_index=final_session,
                instrument_index=instrument_index,
            )
            assert_same_cell(vector_row[instrument_index], scalar)

    core = core_input(panel)
    manifest = fixture_manifest("full_260d")
    assert core.content_hash == manifest["input_hash"]
    assert core.common_calendar_hash == manifest["calendar_content_hash"]
    assert core.universe_content_hash == manifest["current_universe_content_hash"]
    assert panel.universe_history.history_content_hash == manifest["history_content_hash"]
    envelope = evaluate_formulaic_alpha101(core_input=core, panel=panel)
    assert envelope.package_spec == FORMULAIC_ALPHA101
    assert envelope.feature_order == FORMULAIC_ALPHA101_FEATURE_ORDER
    assert len(envelope.rows) == len(FULL_INSTRUMENTS) * 101
    assert envelope.manifest.instrument_count == len(FULL_INSTRUMENTS)
    assert envelope.manifest.definition_registry_hash == (
        FORMULAIC_ALPHA101.required_definition_registry_hash
    )
    assert envelope.manifest.computation_manifest_hash == ALPHA101_COMPUTATION_MANIFEST_HASH
    assert (
        "computation_manifest_hash" not in inspect.signature(evaluate_formulaic_alpha101).parameters
    )
    assert envelope == evaluate_formulaic_alpha101(core_input=core, panel=panel)
    assert {row.availability_state for row in envelope.rows} == {
        FeatureAvailabilityState.OBSERVED,
        FeatureAvailabilityState.MISSING,
        FeatureAvailabilityState.NOT_APPLICABLE,
    }
    assert all(
        row.value_winsorized is None
        and row.value_standardized is None
        and row.neutralized_diagnostic is None
        for row in envelope.rows
    )
    assert all(row.missing_reason_code != Alpha101Reason.WINDOW_INCOMPLETE for row in envelope.rows)
    tampered = envelope.model_dump()
    tampered["rows"][0]["value_raw"] = 999.0
    with pytest.raises(ValidationError, match=r"identity|hash|row"):
        CoreRawFeatureEnvelope.model_validate(tampered)
    tampered = envelope.model_dump()
    tampered["manifest"]["computation_manifest_hash"] = "sha256:" + "0" * 64
    with pytest.raises(ValidationError, match=r"identity|hash|manifest"):
        CoreRawFeatureEnvelope.model_validate(tampered)
    assert_envelope_matches_golden(envelope, "full_260d")


def test_edge_65d_keeps_calendar_positions_and_stable_failure_reasons() -> None:
    panel = edge_panel()
    evaluator = Alpha101Evaluator(panel)
    assert_evaluator_matches_golden(panel, evaluator, "edge_65d")
    final = len(panel.sessions) - 1
    alpha19 = evaluator.evaluate(ALPHA101_DEFINITIONS[18])[final]
    assert {cell.reason for cell in alpha19} == {Alpha101Reason.WINDOW_INCOMPLETE}

    # The suspension remains in the shared-session window; it is never skipped.
    assert panel.input_matrix("returns")[52][0].reason == Alpha101Reason.NO_LEGAL_BAR
    assert panel.input_matrix("returns")[53][0].reason == Alpha101Reason.NO_LEGAL_BAR
    # Explicit zero volume is observed as zero, but vwap division fails closed.
    assert panel.input_matrix("volume")[-1][1] == Alpha101Cell(0.0)
    assert panel.input_matrix("vwap")[-1][1].reason == Alpha101Reason.ZERO_DENOMINATOR
    # A legal one-price bar remains data; only real formula denominators may fail.
    assert panel.input_matrix("close")[-1][2].state == FeatureAvailabilityState.OBSERVED

    core = core_input(panel)
    manifest = fixture_manifest("edge_65d")
    assert core.content_hash == manifest["input_hash"]
    assert core.common_calendar_hash == manifest["calendar_content_hash"]
    assert core.universe_content_hash == manifest["current_universe_content_hash"]
    assert panel.universe_history.history_content_hash == manifest["history_content_hash"]
    envelope = evaluate_formulaic_alpha101(core_input=core, panel=panel)
    assert len(envelope.rows) == len(EDGE_INSTRUMENTS) * 101
    assert envelope.manifest.missing_count > 0
    assert envelope.manifest.not_applicable_count > 0
    assert any(row.missing_reason_code == Alpha101Reason.NONFINITE for row in envelope.rows)
    assert_envelope_matches_golden(envelope, "edge_65d")


def test_point_in_time_industry_is_strict_and_l3_never_falls_back() -> None:
    panel = pit_panel()
    final = len(panel.sessions) - 1
    assert panel.industry_groups(final - 1, "sector")[0] == "old-l1"
    assert panel.industry_groups(final - 1, "industry")[0] == "old-l2"
    # Published after the 16:00 bar but before the explicit 18:00 cutoff: visible.
    assert panel.industry_groups(final, "sector") == ("future-l1", "visible-l1", None)
    assert panel.industry_groups(final, "industry") == ("future-l2", "visible-l2", None)
    assert panel.industry_groups(final, "subindustry") == (None, None, None)

    evaluator = Alpha101Evaluator(panel)
    assert_evaluator_matches_golden(panel, evaluator, "pit_industry")
    by_ordinal = {
        definition.ordinal: evaluator.evaluate(definition)[final]
        for definition in ALPHA101_DEFINITIONS
        if definition.industry_levels
    }
    for ordinal in (48, 90, 100):
        assert {cell.reason for cell in by_ordinal[ordinal]} == {Alpha101Reason.SW_L3_UNAVAILABLE}
        assert (
            evaluator.evaluate(ALPHA101_DEFINITIONS[ordinal - 1])[0][0].reason
            == Alpha101Reason.SW_L3_UNAVAILABLE
        )
    assert {cell.state for cell in by_ordinal[67]} == {FeatureAvailabilityState.NOT_APPLICABLE}
    assert {cell.reason for cell in by_ordinal[67][:2]} == {Alpha101Reason.SW_L3_UNAVAILABLE}

    all_industry_ordinals = {
        48,
        58,
        59,
        63,
        67,
        69,
        70,
        76,
        79,
        80,
        82,
        87,
        89,
        90,
        91,
        93,
        97,
        100,
    }
    for ordinal in all_industry_ordinals:
        assert by_ordinal[ordinal][2].state == FeatureAvailabilityState.NOT_APPLICABLE

    manifest = fixture_manifest("pit_industry")
    core = core_input(panel)
    assert core.content_hash == manifest["input_hash"]
    assert core.common_calendar_hash == manifest["calendar_content_hash"]
    assert core.universe_content_hash == manifest["current_universe_content_hash"]
    assert panel.universe_history.history_content_hash == manifest["history_content_hash"]
    assert_envelope_matches_golden(
        evaluate_formulaic_alpha101(core_input=core, panel=panel),
        "pit_industry",
    )


def test_arbitrary_l3_strings_cannot_activate_the_unavailable_capability(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    baseline = full_panel()

    def rebuild(prefix: str) -> Alpha101Panel:
        injected = []
        for index, item in enumerate(baseline.industries):
            payload = item.model_dump()
            payload["sw_l3"] = f"{prefix}-l3-{index % 3}"
            injected.append(IndustryMembershipObservation.model_validate(payload))
        return Alpha101Panel(
            common_sessions=baseline.sessions,
            universe_history=baseline.universe_history,
            bar_dataset_name=baseline.bar_dataset_name,
            industry_dataset_name=baseline.industry_dataset_name,
            instruments=baseline.instruments,
            observations=baseline.observations,
            industries=injected,
        )

    injected = rebuild("injected")
    renamed = rebuild("renamed")
    final = len(baseline.sessions) - 1
    evaluators = tuple(Alpha101Evaluator(panel) for panel in (baseline, injected, renamed))

    for ordinal in (48, 67, 90, 100):
        rows = tuple(
            evaluator.evaluate(ALPHA101_DEFINITIONS[ordinal - 1])[final] for evaluator in evaluators
        )
        assert all(
            cell.state == FeatureAvailabilityState.NOT_APPLICABLE for row in rows for cell in row
        )
        assert all(
            cell.reason == Alpha101Reason.SW_L3_UNAVAILABLE for row in rows for cell in row[:-1]
        )

    for definition in ALPHA101_DEFINITIONS:
        if definition.industry_levels:
            continue
        baseline_row, injected_row, renamed_row = (
            evaluator.evaluate(definition)[final] for evaluator in evaluators
        )
        assert injected_row == baseline_row
        assert renamed_row == baseline_row

    injected_envelope = evaluate_formulaic_alpha101(
        core_input=core_input(injected),
        panel=injected,
    )
    renamed_envelope = evaluate_formulaic_alpha101(
        core_input=core_input(renamed),
        panel=renamed,
    )
    assert injected_envelope.manifest.computation_manifest_hash == (
        ALPHA101_COMPUTATION_MANIFEST_HASH
    )
    assert renamed_envelope.manifest.computation_manifest_hash == (
        ALPHA101_COMPUTATION_MANIFEST_HASH
    )
    monkeypatch.setattr(inputs_module, "L3_CAPABILITY_STATUS", "available")
    with pytest.raises(ValueError, match="unknown Alpha101 L3 capability status"):
        injected.industry_groups(final, "subindustry")


def test_shared_calendar_rejects_deleted_sessions_and_old_semantics_hash() -> None:
    panel = full_panel()
    core = core_input(panel)
    truncated = full_panel(drop_session_index=100)
    assert truncated.sessions[-1] == panel.sessions[-1] == core.decision_date
    assert len(truncated.sessions) == len(panel.sessions) - 1
    assert panel.sessions[100] not in truncated.sessions

    with pytest.raises(ValueError, match="calculation sessions do not match"):
        evaluate_formulaic_alpha101(core_input=core, panel=truncated)
    with pytest.raises(ValueError, match="calculation sessions do not match"):
        evaluate_formulaic_alpha101(core_input=core_input(truncated), panel=panel)

    payload = core.common_calendar.model_dump()
    payload["content_hash"] = (
        "sha256:3904e03a09b307b4338161931cb713be866a5b5067f3f5acdcfa0051d3487eb8"
    )
    with pytest.raises(ValidationError, match="content hash mismatch"):
        CoreCommonCalendar.model_validate(payload)

    changed = freeze_core_common_calendar(
        calendar_id=core.common_calendar_id,
        sessions=panel.sessions[:100] + panel.sessions[101:],
    )
    assert changed.content_hash != core.common_calendar_hash


def test_bar_and_industry_availability_must_respect_core_and_dataset_cutoffs() -> None:
    baseline = full_panel()
    late_bar = full_panel(late_bar_at=(100, 0))
    with pytest.raises(ValueError, match="bar rows do not match"):
        evaluate_formulaic_alpha101(core_input=core_input(baseline), panel=late_bar)
    with pytest.raises(ValueError, match="bar crosses"):
        evaluate_formulaic_alpha101(core_input=core_input(late_bar), panel=late_bar)

    pit = pit_panel()
    with pytest.raises(ValueError, match="industry observation crosses"):
        evaluate_formulaic_alpha101(
            core_input=core_input(pit, dataset_cutoff_time=time(16)),
            panel=pit,
        )
    late_industry = pit_panel(late_industry=True)
    with pytest.raises(ValueError, match="industry rows do not match"):
        evaluate_formulaic_alpha101(
            core_input=core_input(pit),
            panel=late_industry,
        )
    with pytest.raises(ValueError, match="industry observation crosses"):
        evaluate_formulaic_alpha101(
            core_input=core_input(late_industry),
            panel=late_industry,
        )


def test_current_public_u0_and_historical_manifest_are_separate_identities() -> None:
    assert "research_member" not in Alpha101DailyObservation.model_fields
    panel = full_panel()
    core = core_input(panel)
    assert core.universe_content_hash == core_universe_content_hash(
        panel.universe_history.current_decisions()
    )
    assert core.universe_content_hash != panel.universe_history.history_content_hash
    assert evaluate_formulaic_alpha101(core_input=core, panel=panel)
    assert panel.members(0)[-1] is False
    assert panel.members(3)[-1] is True

    historical_flip = full_panel(flip_membership_at=(100, 0))
    assert historical_flip.members(100)[0] is not panel.members(100)[0]
    assert core_universe_content_hash(historical_flip.universe_history.current_decisions()) == (
        core.universe_content_hash
    )
    with pytest.raises(ValueError, match="history does not match"):
        evaluate_formulaic_alpha101(core_input=core, panel=historical_flip)

    current_flip = full_panel(flip_membership_at=(len(panel.sessions) - 1, 0))
    with pytest.raises(ValueError, match="current U0 decisions do not match"):
        evaluate_formulaic_alpha101(core_input=core, panel=current_flip)


def test_u0_history_rejects_duplicate_future_and_input_order_attacks() -> None:
    history = full_panel(session_count=5).universe_history
    payload = history.model_dump()
    payload["decisions"] = tuple(reversed(payload["decisions"]))
    with pytest.raises(ValidationError, match="canonical axis order"):
        Alpha101UniverseHistory.model_validate(payload)
    with pytest.raises(ValueError, match="canonical axis order"):
        freeze_alpha101_universe_history(
            common_sessions=history.common_sessions,
            instruments=history.instruments,
            decisions=tuple(reversed(history.decisions)),
        )

    payload = history.model_dump()
    decisions = list(payload["decisions"])
    decisions[1] = decisions[0]
    payload["decisions"] = tuple(decisions)
    with pytest.raises(ValidationError, match="exactly once"):
        Alpha101UniverseHistory.model_validate(payload)

    payload = history.model_dump()
    decisions = list(payload["decisions"])
    decisions[0]["input_cutoff"] += timedelta(days=1)
    payload["decisions"] = tuple(decisions)
    with pytest.raises(ValidationError, match="same-day cutoff"):
        Alpha101UniverseHistory.model_validate(payload)


def test_prefix_and_formula_chunk_order_are_causal_and_deterministic() -> None:
    full = full_panel()
    prefix = full_panel(session_count=180)
    full_evaluator = Alpha101Evaluator(full)
    prefix_evaluator = Alpha101Evaluator(prefix)
    for definition in ALPHA101_DEFINITIONS:
        full_row = full_evaluator.evaluate(definition)[179]
        prefix_row = prefix_evaluator.evaluate(definition)[-1]
        for actual, expected in zip(full_row, prefix_row, strict=True):
            assert_same_cell(actual, expected)

    edge = edge_panel()
    forward = Alpha101Evaluator(edge)
    reverse = Alpha101Evaluator(edge)
    forward_rows = {
        definition.ordinal: forward.evaluate(definition)[-1]
        for start in range(0, 101, 17)
        for definition in ALPHA101_DEFINITIONS[start : start + 17]
    }
    reverse_rows = {
        definition.ordinal: reverse.evaluate(definition)[-1]
        for definition in reversed(ALPHA101_DEFINITIONS)
    }
    assert forward_rows == reverse_rows


def test_input_rows_are_bound_and_security_local_formulas_do_not_bleed() -> None:
    panel = full_panel()
    observations = list(panel.observations)
    target_index = (len(panel.sessions) - 1) * len(panel.instruments)
    original = observations[target_index]
    payload = original.model_dump()
    assert original.research_open_index is not None
    payload["research_open_index"] = original.research_open_index * 1.0001
    observations[target_index] = Alpha101DailyObservation.model_validate(payload)
    changed = Alpha101Panel(
        common_sessions=panel.sessions,
        universe_history=panel.universe_history,
        bar_dataset_name=panel.bar_dataset_name,
        industry_dataset_name=panel.industry_dataset_name,
        instruments=panel.instruments,
        observations=observations,
        industries=panel.industries,
    )
    assert changed.bar_content_hash != panel.bar_content_hash
    with pytest.raises(ValueError, match="bar rows do not match"):
        evaluate_formulaic_alpha101(core_input=core_input(panel), panel=changed)

    definition = ALPHA101_DEFINITIONS[100]
    baseline_row = Alpha101Evaluator(panel).evaluate(definition)[-1]
    changed_row = Alpha101Evaluator(changed).evaluate(definition)[-1]
    assert baseline_row[0] != changed_row[0]
    assert baseline_row[1:] == changed_row[1:]


def test_ambiguous_or_changed_industry_evidence_fails_closed() -> None:
    panel = full_panel()
    payload = panel.industries[0].model_dump()
    payload["source_record_hash"] = "sha256:" + "f" * 64
    payload["sw_l1"] = "conflicting-l1"
    conflicting = type(panel.industries[0]).model_validate(payload)

    def rebuild(
        industries: tuple[IndustryMembershipObservation, ...],
    ) -> Alpha101Panel:
        return Alpha101Panel(
            common_sessions=panel.sessions,
            universe_history=panel.universe_history,
            bar_dataset_name=panel.bar_dataset_name,
            industry_dataset_name=panel.industry_dataset_name,
            instruments=panel.instruments,
            observations=panel.observations,
            industries=industries,
        )

    with pytest.raises(ValueError, match="ambiguous point-in-time"):
        rebuild((*panel.industries, conflicting))

    replaced = rebuild((conflicting, *panel.industries[1:]))
    assert replaced.industry_content_hash != panel.industry_content_hash
    with pytest.raises(ValueError, match="industry rows do not match"):
        evaluate_formulaic_alpha101(core_input=core_input(panel), panel=replaced)

    expiring_payload = panel.industries[0].model_dump()
    expiring_payload["valid_to"] = panel.sessions[-1]
    expiring = IndustryMembershipObservation.model_validate(expiring_payload)
    expired = rebuild((expiring, *panel.industries[1:]))
    assert expired.industry_groups(len(panel.sessions) - 2, "sector")[0] is not None
    assert expired.industry_groups(len(panel.sessions) - 1, "sector")[0] is None
