from __future__ import annotations

from dataclasses import replace
from functools import lru_cache

import pytest
from test_core_feature_processing_period_support import (
    INSTRUMENTS,
    exact_period_panel_parents,
)
from test_core_feature_selection_attack_support import forged_bootstrap_p_value
from test_core_feature_selection_period_attack_support import (
    rehash_projection,
    representative_attack,
)
from test_core_feature_selection_production_support import production_selection_case

from astramind_mini.strategy_research.core.feature_processing import (
    CoreProcessedFeaturePanelParents,
    rebuild_core_processed_feature_panel,
)
from astramind_mini.strategy_research.core.feature_selection import (
    CoreFeatureSelectionManifest,
    CoreFeatureSelectionParents,
    CoreFrozenJointFeatureDefinitionParents,
    CorePeriodJointMatrixProjection,
    CorePeriodJointProjectionParents,
    rebuild_core_frozen_joint_feature_definition,
    rebuild_core_period_joint_projection,
    validate_core_frozen_joint_feature_definition,
    validate_core_period_joint_projection,
)
from astramind_mini.strategy_research.core.labels import CoreLabelHorizon
from astramind_mini.strategy_research.core.packages import (
    ASTRAMIND_F0,
    FORMULAIC_ALPHA101,
    QLIB_ALPHA158,
)

PACKAGES = (
    ASTRAMIND_F0.package_id,
    QLIB_ALPHA158.package_id,
    FORMULAIC_ALPHA101.package_id,
)
TARGETS = (
    PACKAGES[:2],
    (PACKAGES[0], PACKAGES[2]),
    PACKAGES[1:],
    PACKAGES,
)


def test_all_pair_and_triple_definitions_project_exact_new_period_parents() -> None:
    panel_parents = {package: exact_period_panel_parents(package) for package in PACKAGES}
    panels = {
        package: rebuild_core_processed_feature_panel(proof)
        for package, proof in panel_parents.items()
    }
    for target in TARGETS:
        definition_parents = _definition_parents(target)
        definition = rebuild_core_frozen_joint_feature_definition(definition_parents)
        proof = CorePeriodJointProjectionParents.freeze(
            definition=definition,
            definition_parents=definition_parents,
            period_panels={package: panels[package] for package in target},
            period_panel_parents={package: panel_parents[package] for package in target},
            decision_date=panels[target[0]].decision_dates[-1],
        )
        projection = rebuild_core_period_joint_projection(proof)
        assert validate_core_period_joint_projection(projection, proof) == projection
        assert tuple(item.package_id for item in projection.package_bindings) == target
        assert projection.row_order == INSTRUMENTS
        assert projection.column_order == definition.model_columns


def test_joint_definition_rejects_selection_horizon_order_and_representative_attacks() -> None:
    parents = _definition_parents(PACKAGES)
    definition = rebuild_core_frozen_joint_feature_definition(parents)
    forged_selections = dict(parents.selections)
    forged_selections[PACKAGES[0]] = forged_bootstrap_p_value(forged_selections[PACKAGES[0]])
    with pytest.raises(ValueError, match="reconstructed true parents"):
        rebuild_core_frozen_joint_feature_definition(replace(parents, selections=forged_selections))
    with pytest.raises(ValueError):
        rebuild_core_frozen_joint_feature_definition(replace(parents, horizon=CoreLabelHorizon.H60))
    with pytest.raises(ValueError, match="canonical target"):
        rebuild_core_frozen_joint_feature_definition(
            replace(parents, package_ids=(PACKAGES[1], PACKAGES[0]))
        )
    forged_definition = representative_attack(definition)
    with pytest.raises(ValueError, match="frozen joint definition differs"):
        validate_core_frozen_joint_feature_definition(forged_definition, parents)


def test_joint_period_projection_rejects_cross_package_u0_and_package_omission() -> None:
    definition_parents = _definition_parents(PACKAGES)
    definition = rebuild_core_frozen_joint_feature_definition(definition_parents)
    period_parents = {package: exact_period_panel_parents(package) for package in PACKAGES}
    period_parents[PACKAGES[1]] = exact_period_panel_parents(
        PACKAGES[1],
        instruments=("A", "B", "D"),
    )
    panels = {
        package: rebuild_core_processed_feature_panel(proof)
        for package, proof in period_parents.items()
    }
    with pytest.raises(ValueError, match="share exact U0"):
        rebuild_core_period_joint_projection(
            CorePeriodJointProjectionParents.freeze(
                definition=definition,
                definition_parents=definition_parents,
                period_panels=panels,
                period_panel_parents=period_parents,
                decision_date=panels[PACKAGES[0]].decision_dates[-1],
            )
        )
    with pytest.raises(ValueError, match="every and only declared package"):
        rebuild_core_period_joint_projection(
            CorePeriodJointProjectionParents.freeze(
                definition=definition,
                definition_parents=definition_parents,
                period_panels={package: panels[package] for package in PACKAGES[:-1]},
                period_panel_parents={
                    package: period_parents[package] for package in PACKAGES[:-1]
                },
                decision_date=panels[PACKAGES[0]].decision_dates[-1],
            )
        )


def test_joint_period_projection_rejects_fully_rehashed_output_and_uses_base_bytes() -> None:
    proof = _period_proof(PACKAGES)
    projection = rebuild_core_period_joint_projection(proof)
    data = projection.model_dump()
    values = list(data["values"])
    values[0] = (999.0, *values[0][1:])
    data["values"] = tuple(values)
    forged = rehash_projection(data)
    with pytest.raises(ValueError, match="period joint projection differs"):
        validate_core_period_joint_projection(forged, proof)

    class ModelDumpOverride(CorePeriodJointMatrixProjection):
        def model_dump(self, *args: object, **kwargs: object) -> dict[str, object]:
            return {"forged": True}

    subclass = ModelDumpOverride.model_construct(**projection.__dict__)
    assert validate_core_period_joint_projection(subclass, proof) == projection


@lru_cache(maxsize=2)
def _cases(
    horizon: CoreLabelHorizon,
) -> dict[
    str,
    tuple[CoreFeatureSelectionParents, CoreFeatureSelectionManifest],
]:
    return {
        package: production_selection_case(
            package,
            horizon,
            profile="full_ready" if package == PACKAGES[0] else "single",
        )
        for package in PACKAGES
    }


def _definition_parents(
    target: tuple[str, ...],
) -> CoreFrozenJointFeatureDefinitionParents:
    cases = _cases(CoreLabelHorizon.H20)
    return CoreFrozenJointFeatureDefinitionParents.freeze(
        horizon=CoreLabelHorizon.H20,
        package_ids=target,
        selections={package: cases[package][1] for package in PACKAGES},
        selection_parents={package: cases[package][0] for package in PACKAGES},
    )


def _period_proof(target: tuple[str, ...]) -> CorePeriodJointProjectionParents:
    definition_parents = _definition_parents(target)
    definition = rebuild_core_frozen_joint_feature_definition(definition_parents)
    period_parents: dict[str, CoreProcessedFeaturePanelParents] = {
        package: exact_period_panel_parents(package) for package in target
    }
    panels = {
        package: rebuild_core_processed_feature_panel(value)
        for package, value in period_parents.items()
    }
    return CorePeriodJointProjectionParents.freeze(
        definition=definition,
        definition_parents=definition_parents,
        period_panels=panels,
        period_panel_parents=period_parents,
        decision_date=panels[target[0]].decision_dates[-1],
    )
