from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

import pytest
from test_core_feature_processing_period_attack_support import (
    columns,
    rehash_definition,
    rehash_envelope,
    rehash_panel,
    row_order_attack,
    state_attack,
    value_attack,
)
from test_core_feature_processing_period_support import (
    INSTRUMENTS,
    exact_period_panel_parents,
)
from test_core_feature_selection_attack_support import forged_bootstrap_p_value
from test_core_feature_selection_production_support import production_selection_case

from astramind_mini.strategy_research.core.feature_processing import (
    CoreFeatureViewKind,
    CoreFrozenFeatureDefinitionParents,
    CorePeriodFeatureProjectionParents,
    rebuild_core_frozen_feature_definition,
    rebuild_core_period_feature_projection,
    rebuild_core_processed_feature_envelope,
    rebuild_core_processed_feature_panel,
    validate_core_frozen_feature_definition,
    validate_core_period_feature_projection,
    validate_core_processed_feature_envelope,
    validate_core_processed_feature_panel,
)
from astramind_mini.strategy_research.core.labels import CoreLabelHorizon
from astramind_mini.strategy_research.core.packages import ASTRAMIND_F0

PACKAGE = ASTRAMIND_F0.package_id


def test_full_and_selected_definitions_project_exact_new_period_parents() -> None:
    selection_parents, selection = production_selection_case(
        PACKAGE,
        CoreLabelHorizon.H20,
        profile="full_ready",
    )
    panel_parents = exact_period_panel_parents(PACKAGE)
    panel = rebuild_core_processed_feature_panel(panel_parents)
    assert validate_core_processed_feature_panel(panel, panel_parents) == panel
    projections = []
    for view_kind in (CoreFeatureViewKind.FULL, CoreFeatureViewKind.SELECTED):
        definition_parents = CoreFrozenFeatureDefinitionParents(
            selection,
            selection_parents,
            view_kind,
        )
        definition = rebuild_core_frozen_feature_definition(definition_parents)
        proof = CorePeriodFeatureProjectionParents(
            definition,
            definition_parents,
            panel,
            panel_parents,
            panel.decision_dates[-1],
        )
        projection = rebuild_core_period_feature_projection(proof)
        assert validate_core_period_feature_projection(projection, proof) == projection
        assert projection.definition_id == definition.definition_id
        assert projection.period_panel_manifest_id == panel.panel_manifest_id
        assert projection.row_order == INSTRUMENTS
        assert projection.column_order == definition.model_columns
        projections.append(projection)
    full, selected = projections
    assert len(full.column_order) == 3 * ASTRAMIND_F0.canonical_dimension
    assert len(selected.column_order) == 3
    assert full.values[1][1:3] == (1.0, 0.0)
    assert full.values[2][1:3] == (0.0, 1.0)
    assert len(selected.values[0]) == len(definition.model_columns)


def test_period_envelope_rebuild_rejects_rehashed_value_state_u0_and_order_attacks() -> None:
    daily = exact_period_panel_parents(PACKAGE).daily_parents[0]
    expected = rebuild_core_processed_feature_envelope(daily)
    attacks = (
        value_attack(expected),
        state_attack(expected),
        rehash_envelope({**expected.model_dump(), "universe_content_hash": "sha256:" + "f" * 64}),
        row_order_attack(expected),
    )
    for attack in attacks:
        with pytest.raises(ValueError, match="exact processing parents"):
            validate_core_processed_feature_envelope(attack, daily)


def test_period_projection_rejects_rehashed_panel_and_frozen_definition_attacks() -> None:
    selection_parents, selection = production_selection_case(
        PACKAGE,
        CoreLabelHorizon.H20,
        profile="full_ready",
    )
    definition_parents = CoreFrozenFeatureDefinitionParents(
        selection,
        selection_parents,
        CoreFeatureViewKind.SELECTED,
    )
    definition = rebuild_core_frozen_feature_definition(definition_parents)
    panel_parents = exact_period_panel_parents(PACKAGE)
    panel = rebuild_core_processed_feature_panel(panel_parents)
    forged_envelope = value_attack(
        rebuild_core_processed_feature_envelope(panel_parents.daily_parents[0])
    )
    panel_data = panel.model_dump()
    first = dict(panel_data["entries"][0])
    first["processed_envelope_id"] = forged_envelope.envelope_id
    first["processed_envelope_content_hash"] = forged_envelope.content_hash
    panel_data["entries"] = (first, *panel_data["entries"][1:])
    forged_panel = rehash_panel(panel_data)
    with pytest.raises(ValueError, match="period panel differs"):
        rebuild_core_period_feature_projection(
            CorePeriodFeatureProjectionParents(
                definition,
                definition_parents,
                forged_panel,
                panel_parents,
                panel.decision_dates[-1],
            )
        )

    alternate_feature = next(
        item for item in selection.feature_evidence if item.feature_id != definition.feature_ids[0]
    )
    definition_data = definition.model_dump()
    definition_data["feature_keys"] = (alternate_feature.feature_key,)
    definition_data["feature_ids"] = (alternate_feature.feature_id,)
    definition_data["model_columns"] = columns(alternate_feature.feature_id)
    forged_definition = rehash_definition(definition_data)
    with pytest.raises(ValueError, match="frozen feature definition differs"):
        validate_core_frozen_feature_definition(forged_definition, definition_parents)


def test_definition_rejects_selection_lineage_horizon_and_future_identity_attacks() -> None:
    parents, selection = production_selection_case(
        PACKAGE,
        CoreLabelHorizon.H20,
        profile="full_ready",
    )
    definition_parents = CoreFrozenFeatureDefinitionParents(
        selection,
        parents,
        CoreFeatureViewKind.SELECTED,
    )
    definition = rebuild_core_frozen_feature_definition(definition_parents)
    with pytest.raises(ValueError, match="reconstructed true parents"):
        rebuild_core_frozen_feature_definition(
            replace(
                definition_parents,
                selection_manifest=forged_bootstrap_p_value(selection),
            )
        )
    future_attack = rehash_definition(
        {
            **definition.model_dump(),
            "development_selection_plan_id": "future-plan",
            "development_selection_plan_content_hash": "sha256:" + "a" * 64,
            "development_selection_fold_id": "future-fold",
            "development_selection_spec_hash": "sha256:" + "b" * 64,
            "development_prior_content_hash": "sha256:" + "c" * 64,
            "development_prior_tokenizer_rules_hash": "sha256:" + "d" * 64,
            "development_last_decision_date": (
                definition.development_last_decision_date + timedelta(days=1)
            ),
        }
    )
    with pytest.raises(ValueError, match="frozen feature definition differs"):
        validate_core_frozen_feature_definition(future_attack, definition_parents)
    horizon_attack = rehash_definition({**definition.model_dump(), "horizon": CoreLabelHorizon.H60})
    with pytest.raises(ValueError, match="frozen feature definition differs"):
        validate_core_frozen_feature_definition(horizon_attack, definition_parents)


def test_period_panel_must_start_after_the_development_selection_window() -> None:
    selection_parents, selection = production_selection_case(
        PACKAGE,
        CoreLabelHorizon.H20,
        profile="full_ready",
    )
    definition_parents = CoreFrozenFeatureDefinitionParents(
        selection,
        selection_parents,
        CoreFeatureViewKind.SELECTED,
    )
    definition = rebuild_core_frozen_feature_definition(definition_parents)
    panel_parents = exact_period_panel_parents(
        PACKAGE,
        days=(selection.fold.decision_dates[-1],),
    )
    panel = rebuild_core_processed_feature_panel(panel_parents)
    with pytest.raises(ValueError, match="follow the development selection"):
        rebuild_core_period_feature_projection(
            CorePeriodFeatureProjectionParents(
                definition,
                definition_parents,
                panel,
                panel_parents,
                panel.decision_dates[-1],
            )
        )


def test_period_projection_rejects_a_different_computation_manifest() -> None:
    selection_parents, selection = production_selection_case(
        PACKAGE,
        CoreLabelHorizon.H20,
        profile="full_ready",
    )
    definition_parents = CoreFrozenFeatureDefinitionParents(
        selection,
        selection_parents,
        CoreFeatureViewKind.SELECTED,
    )
    definition = rebuild_core_frozen_feature_definition(definition_parents)
    period_parents = exact_period_panel_parents(
        PACKAGE,
        computation_manifest_hash="sha256:" + "e" * 64,
    )
    panel = rebuild_core_processed_feature_panel(period_parents)
    with pytest.raises(ValueError, match="processing semantics differ"):
        rebuild_core_period_feature_projection(
            CorePeriodFeatureProjectionParents(
                definition,
                definition_parents,
                panel,
                period_parents,
                panel.decision_dates[-1],
            )
        )
