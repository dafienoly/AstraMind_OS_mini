from __future__ import annotations

import copy
import math
from datetime import date, timedelta

import pytest
from test_core_feature_selection_support import (
    frozen_envelopes,
    frozen_panel,
    frozen_selection,
)

from astramind_mini.strategy_research.application.identity import research_hash
from astramind_mini.strategy_research.core.feature_processing import (
    CoreProcessedFeatureEnvelope,
    CoreProcessedFeatureRow,
    CoreProcessingSpec,
)
from astramind_mini.strategy_research.core.feature_selection import (
    CoreFeatureSelectionManifest,
    CoreSelectionCluster,
    CoreSelectionReason,
    CoreSelectionSpec,
    CoreTurnoverReason,
    feature_turnover,
)
from astramind_mini.strategy_research.core.feature_selection.coverage import (
    CoreCoverageReason,
)
from astramind_mini.strategy_research.core.feature_values import (
    CoreImputationSource,
    FeatureAvailabilityState,
)
from astramind_mini.strategy_research.core.labels import (
    CoreForwardReturnLabelSpec,
    CoreLabelHorizon,
)


def _manifest() -> CoreFeatureSelectionManifest:
    envelopes = frozen_envelopes(
        package_id="manifest-attack-package",
        feature_ids=("F1", "F2"),
        instruments=("A", "B", "C", "D", "E"),
    )
    return frozen_selection(
        panel=frozen_panel(envelopes),
        envelopes=envelopes,
        p_values=(0.01, 0.01),
    )


def _rehashed_data(draft: CoreFeatureSelectionManifest) -> dict[str, object]:
    return _rehashed_mapping(draft.model_dump())


def _rehashed_mapping(data: dict[str, object]) -> dict[str, object]:
    body = {key: value for key, value in data.items() if key not in {"manifest_id", "content_hash"}}
    content_hash = research_hash({"schema": "core-feature-selection-manifest-v1", **body})
    return {
        **data,
        "manifest_id": f"core-selection:{content_hash.removeprefix('sha256:')}",
        "content_hash": content_hash,
    }


def test_fixed_v1_specs_reject_each_class_of_semantic_drift() -> None:
    with pytest.raises(ValueError):
        CoreForwardReturnLabelSpec.model_validate(
            {
                **CoreForwardReturnLabelSpec(horizon=CoreLabelHorizon.H20).model_dump(),
                "entry_offset_common_sessions": 2,
            }
        )
    with pytest.raises(ValueError):
        CoreProcessingSpec.model_validate(
            {
                **CoreProcessingSpec().model_dump(),
                "industry_imputation_minimum_observed": 9,
            }
        )
    with pytest.raises(ValueError):
        CoreSelectionSpec.model_validate(
            {
                **CoreSelectionSpec().model_dump(),
                "bootstrap_replicates": 9999,
            }
        )


def test_manifest_recomputes_bh_complete_linkage_and_representative() -> None:
    manifest = _manifest()
    first = manifest.feature_evidence[0].model_copy(update={"bootstrap_p_value": 0.9})
    bh_attack = manifest.model_copy(
        update={"feature_evidence": (first, manifest.feature_evidence[1])}
    )
    with pytest.raises(ValueError, match="BH evidence"):
        CoreFeatureSelectionManifest.model_validate(_rehashed_data(bh_attack))

    second = manifest.feature_evidence[1].model_copy(
        update={"reason_code": CoreSelectionReason.CLUSTER_REDUNDANT}
    )
    cluster_attack = manifest.model_copy(
        update={
            "feature_evidence": (manifest.feature_evidence[0], second),
            "clusters": (
                CoreSelectionCluster(
                    members=("F1@1.0.0", "F2@1.0.0"),
                    representative="F1@1.0.0",
                ),
            ),
            "selected_feature_keys": ("F1@1.0.0",),
            "selected_feature_ids": ("F1",),
        }
    )
    with pytest.raises(ValueError, match="clusters or representatives"):
        CoreFeatureSelectionManifest.model_validate(_rehashed_data(cluster_attack))


def test_rehashed_coverage_calendar_threshold_and_nonfinite_rankic_attacks_fail() -> None:
    manifest = _manifest()
    threshold_attack = copy.deepcopy(manifest.model_dump())
    coverage = threshold_attack["feature_evidence"][0]["coverage"]
    daily = list(coverage["daily"])
    daily[0] = {
        **daily[0],
        "passes_date_threshold": False,
        "reason_code": CoreCoverageReason.COVERAGE_GATE_FAILED,
    }
    coverage["daily"] = tuple(daily)
    coverage["passing_date_count"] -= 1
    coverage["passing_date_ratio"] = coverage["passing_date_count"] / len(daily)
    with pytest.raises(ValueError, match="coverage threshold"):
        CoreFeatureSelectionManifest.model_validate(_rehashed_mapping(threshold_attack))

    calendar_attack = copy.deepcopy(manifest.model_dump())
    coverage = calendar_attack["feature_evidence"][0]["coverage"]
    daily = list(coverage["daily"])
    daily[0] = {
        **daily[0],
        "decision_date": manifest.fold.decision_dates[0] - timedelta(days=1),
    }
    coverage["daily"] = tuple(daily)
    with pytest.raises(ValueError, match="exact feature and fold calendar"):
        CoreFeatureSelectionManifest.model_validate(_rehashed_mapping(calendar_attack))

    nonfinite_attack = copy.deepcopy(manifest.model_dump())
    rankic = list(nonfinite_attack["feature_evidence"][0]["daily_rank_ic"])
    rankic[0] = {**rankic[0], "rank_ic": math.inf, "signed_rank_ic": math.inf}
    nonfinite_attack["feature_evidence"][0]["daily_rank_ic"] = tuple(rankic)
    with pytest.raises(ValueError, match="less than or equal to 1"):
        CoreFeatureSelectionManifest.model_validate(_rehashed_mapping(nonfinite_attack))


def test_turnover_evidence_binds_every_adjacent_date_and_stage_p_identities() -> None:
    manifest = _manifest()
    evidence = manifest.feature_evidence[0]
    assert len(evidence.turnover_transitions) == 179
    assert all(
        item.previous_n_day == item.current_n_day == item.n_common == 5
        and item.valid
        and item.turnover_ratio == 0.0
        for item in evidence.turnover_transitions
    )
    shortened = evidence.model_copy(
        update={
            "turnover_transitions": evidence.turnover_transitions[1:],
            "turnover_valid_transitions": 178,
        }
    )
    turnover_attack = manifest.model_copy(
        update={"feature_evidence": (shortened, manifest.feature_evidence[1])}
    )
    with pytest.raises(ValueError, match="every adjacent fold date"):
        CoreFeatureSelectionManifest.model_validate(_rehashed_data(turnover_attack))

    prior_attack = manifest.model_copy(update={"prior_content_hash": "sha256:" + "0" * 64})
    with pytest.raises(ValueError, match="Stage P identities"):
        CoreFeatureSelectionManifest.model_validate(_rehashed_data(prior_attack))
    tokenizer_attack = manifest.model_copy(
        update={"prior_tokenizer_rules_hash": "sha256:" + "0" * 64}
    )
    with pytest.raises(ValueError, match="Stage P identities"):
        CoreFeatureSelectionManifest.model_validate(_rehashed_data(tokenizer_attack))


def test_turnover_records_daily_counts_and_each_invalid_reason() -> None:
    start = date(2025, 1, 1)
    memberships = (
        ("A", "B", "C", "D", "E"),
        ("A",),
        ("A", "B", "C", "D", "E"),
        ("B", "C", "D", "E", "F"),
        ("B", "C", "D", "E", "F"),
    )
    envelopes = tuple(
        CoreProcessedFeatureEnvelope.model_construct(
            decision_date=start + timedelta(days=index),
            rows=tuple(
                _observed_row(instrument, position) for position, instrument in enumerate(ids)
            ),
        )
        for index, ids in enumerate(memberships)
    )
    turnover, valid_count, transitions = feature_turnover(envelopes, feature_id="F")
    assert turnover is None
    assert valid_count == 1
    assert [item.reason_code for item in transitions] == [
        CoreTurnoverReason.CURRENT_CROSS_SECTION_INSUFFICIENT,
        CoreTurnoverReason.PREVIOUS_CROSS_SECTION_INSUFFICIENT,
        CoreTurnoverReason.COMMON_INSTRUMENTS_INSUFFICIENT,
        CoreTurnoverReason.AVAILABLE,
    ]
    assert [(item.previous_n_day, item.current_n_day, item.n_common) for item in transitions] == [
        (5, 1, 1),
        (1, 5, 1),
        (5, 5, 4),
        (5, 5, 5),
    ]


def _observed_row(instrument: str, value: int) -> CoreProcessedFeatureRow:
    return CoreProcessedFeatureRow(
        instrument_id=instrument,
        feature_id="F",
        feature_definition_version="1.0.0",
        availability_state=FeatureAvailabilityState.OBSERVED,
        value_raw=float(value),
        value_winsorized=float(value),
        value_standardized_observed=float(value),
        model_value=float(value),
        imputation_source=CoreImputationSource.NONE,
        is_missing=False,
        is_not_applicable=False,
    )
