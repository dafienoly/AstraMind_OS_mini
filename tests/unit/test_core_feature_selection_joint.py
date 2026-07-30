from __future__ import annotations

from datetime import date, timedelta

import pytest

from astramind_mini.strategy_research.application.identity import research_hash
from astramind_mini.strategy_research.core.feature_processing import (
    CoreProcessedFeatureEnvelope,
    CoreProcessedFeatureRow,
)
from astramind_mini.strategy_research.core.feature_selection import (
    STAGE_P_PRIORS_CONTENT_HASH,
    CoreCorrelationStatus,
    CoreFeatureSelectionEvidence,
    CoreFeatureSelectionManifest,
    CoreJointViewStatus,
    CoreLabelBatchReference,
    CoreProcessedDayReference,
    CoreSelectionFold,
    build_core_joint_selected_view_manifests,
    pair_correlation_evidence,
    project_core_joint_selected_matrix,
)
from astramind_mini.strategy_research.core.feature_values import (
    CoreImputationSource,
    FeatureAvailabilityState,
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
FEATURES = {
    PACKAGES[0]: "F0_TEST",
    PACKAGES[1]: "A158_TEST",
    PACKAGES[2]: "A101_TEST",
}
INSTRUMENTS = ("A", "B", "C", "D", "E")
START = date(2025, 1, 2)


def _hash(value: object) -> str:
    return research_hash({"fixture": value})


def _envelope(
    package: str,
    feature_id: str,
    index: int,
    *,
    universe_hash: str | None = None,
) -> CoreProcessedFeatureEnvelope:
    day = START + timedelta(days=index)
    rows = tuple(
        CoreProcessedFeatureRow(
            instrument_id=instrument,
            feature_id=feature_id,
            feature_definition_version="1.0.0",
            availability_state=FeatureAvailabilityState.OBSERVED,
            value_raw=float(position + index),
            value_winsorized=float(position + index),
            value_standardized_observed=float(position),
            model_value=float(position),
            imputation_source=CoreImputationSource.NONE,
            is_missing=False,
            is_not_applicable=False,
        )
        for position, instrument in enumerate(INSTRUMENTS)
    )
    return CoreProcessedFeatureEnvelope.model_construct(
        envelope_id=f"processed-{package}-{index}",
        content_hash=_hash(("processed", package, index, universe_hash)),
        decision_date=day,
        package_id=package,
        universe_content_hash=universe_hash or _hash(("u0", index)),
        feature_order=(feature_id,),
        instrument_order=INSTRUMENTS,
        rows=rows,
        blocked_feature_ids=(),
    )


def _panel_set() -> dict[str, tuple[CoreProcessedFeatureEnvelope, ...]]:
    return {
        package: tuple(_envelope(package, FEATURES[package], index) for index in range(60))
        for package in PACKAGES
    }


def _selection(
    package: str,
    horizon: CoreLabelHorizon,
    envelopes: tuple[CoreProcessedFeatureEnvelope, ...],
    *,
    selected: bool = True,
) -> CoreFeatureSelectionManifest:
    feature_id = FEATURES[package]
    feature_key = f"{package}:{feature_id}@1.0.0"
    evidence = CoreFeatureSelectionEvidence.model_construct(
        feature_key=feature_key,
        feature_id=feature_id,
        definition_version="1.0.0",
        direction_consistent=True,
        complexity=1,
        coverage_mean=1.0,
        turnover=0.0,
        stability=1.0,
    )
    dates = tuple(item.decision_date for item in envelopes)
    processed_days = tuple(
        CoreProcessedDayReference(
            decision_date=item.decision_date,
            processed_envelope_id=item.envelope_id,
            processed_envelope_content_hash=item.content_hash,
            universe_content_hash=item.universe_content_hash,
        )
        for item in envelopes
    )
    labels = tuple(
        CoreLabelBatchReference(
            decision_date=item.decision_date,
            batch_id=f"label-{horizon}-{index}",
            content_hash=_hash(("label", horizon, index)),
            universe_content_hash=item.universe_content_hash,
        )
        for index, item in enumerate(envelopes)
    )
    selected_keys = (feature_key,) if selected else ()
    selected_ids = (feature_id,) if selected else ()
    return CoreFeatureSelectionManifest.model_construct(
        manifest_id=f"selection-{package}-{horizon}",
        content_hash=_hash(("selection", package, horizon, selected)),
        package_id=package,
        horizon=horizon,
        fold=CoreSelectionFold.model_construct(
            fold_id=f"fold-{horizon}",
            decision_dates=dates,
        ),
        panel_manifest_id=f"panel-{package}",
        panel_content_hash=_hash(("panel", package)),
        prior_content_hash=STAGE_P_PRIORS_CONTENT_HASH,
        processed_days=processed_days,
        label_batches=labels,
        feature_evidence=(evidence,),
        selected_feature_keys=selected_keys,
        selected_feature_ids=selected_ids,
    )


def _selections(
    horizon: CoreLabelHorizon,
    panels: dict[str, tuple[CoreProcessedFeatureEnvelope, ...]],
) -> dict[str, CoreFeatureSelectionManifest]:
    return {package: _selection(package, horizon, panels[package]) for package in PACKAGES}


def test_each_horizon_freezes_four_joint_views_and_projects_direct_matrix() -> None:
    panels = _panel_set()
    h20 = build_core_joint_selected_view_manifests(
        horizon=CoreLabelHorizon.H20,
        selections=_selections(CoreLabelHorizon.H20, panels),
        processed_envelopes=panels,
    )
    h60 = build_core_joint_selected_view_manifests(
        horizon=CoreLabelHorizon.H60,
        selections=_selections(CoreLabelHorizon.H60, panels),
        processed_envelopes=panels,
    )
    assert len(h20) == len(h60) == 4
    assert len({item.joint_view_id for item in (*h20, *h60)}) == 8
    assert all(item.status == CoreJointViewStatus.READY for item in (*h20, *h60))
    triple = next(item for item in h20 if len(item.package_ids) == 3)
    projection = project_core_joint_selected_matrix(
        envelopes={package: panels[package][0] for package in PACKAGES},
        view=triple,
    )
    assert projection.row_order == INSTRUMENTS
    assert projection.column_order == triple.model_columns
    assert len(projection.values[0]) == triple.model_input_dimension
    assert all(isinstance(value, float) for row in projection.values for value in row)


def test_joint_rejects_tail_append_and_cross_package_daily_u0_mismatch() -> None:
    panels = _panel_set()
    selections = _selections(CoreLabelHorizon.H20, panels)
    appended = dict(panels)
    appended[PACKAGES[0]] = (
        *appended[PACKAGES[0]],
        _envelope(PACKAGES[0], FEATURES[PACKAGES[0]], 60),
    )
    with pytest.raises(ValueError, match="frozen selection parents"):
        build_core_joint_selected_view_manifests(
            horizon=CoreLabelHorizon.H20,
            selections=selections,
            processed_envelopes=appended,
        )

    mismatched = dict(panels)
    mismatched_first = _envelope(
        PACKAGES[1],
        FEATURES[PACKAGES[1]],
        0,
        universe_hash=_hash("corrupt-u0"),
    )
    mismatched[PACKAGES[1]] = (mismatched_first, *mismatched[PACKAGES[1]][1:])
    mismatched_selections = dict(selections)
    mismatched_selections[PACKAGES[1]] = _selection(
        PACKAGES[1],
        CoreLabelHorizon.H20,
        mismatched[PACKAGES[1]],
    )
    with pytest.raises(ValueError, match="exact daily U0"):
        build_core_joint_selected_view_manifests(
            horizon=CoreLabelHorizon.H20,
            selections=mismatched_selections,
            processed_envelopes=mismatched,
        )


def test_empty_parent_still_publishes_blocked_joint_identities() -> None:
    panels = _panel_set()
    selections = _selections(CoreLabelHorizon.H20, panels)
    selections[PACKAGES[0]] = _selection(
        PACKAGES[0],
        CoreLabelHorizon.H20,
        panels[PACKAGES[0]],
        selected=False,
    )
    views = build_core_joint_selected_view_manifests(
        horizon=CoreLabelHorizon.H20,
        selections=selections,
        processed_envelopes=panels,
    )
    assert len(views) == 4
    assert sum(item.status == CoreJointViewStatus.BLOCKED for item in views) == 3
    assert len({item.joint_view_id for item in views}) == 4
    blocked = next(item for item in views if item.status == CoreJointViewStatus.BLOCKED)
    with pytest.raises(ValueError, match="blocked"):
        project_core_joint_selected_matrix(
            envelopes={package: panels[package][0] for package in blocked.package_ids},
            view=blocked,
        )


def test_pair_correlation_requires_sixty_valid_daily_cross_sections() -> None:
    panels = _panel_set()
    evidence = pair_correlation_evidence(
        left_feature_key="left@1",
        right_feature_key="right@1",
        left_feature_id=FEATURES[PACKAGES[0]],
        right_feature_id=FEATURES[PACKAGES[1]],
        left_envelopes=panels[PACKAGES[0]][:59],
        right_envelopes=panels[PACKAGES[1]][:59],
    )
    assert evidence.valid_date_count == 59
    assert evidence.status == CoreCorrelationStatus.CORRELATION_EVIDENCE_INSUFFICIENT
    assert evidence.distance is None
