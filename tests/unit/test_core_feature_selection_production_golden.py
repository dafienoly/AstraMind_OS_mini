"""Production replay against the independent 260x24x3 Stage S golden."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from statistics import median
from typing import Any

import pytest
from test_core_feature_selection_production_support import (
    production_validated_selection_case,
)

from astramind_mini.strategy_research.application.identity import research_hash
from astramind_mini.strategy_research.core.feature_selection import (
    rebuild_core_feature_selection,
    spearman,
)
from astramind_mini.strategy_research.core.labels import CoreLabelHorizon
from astramind_mini.strategy_research.core.packages import ASTRAMIND_F0

FIXTURE = (
    Path(__file__).parents[1]
    / "fixtures"
    / "core"
    / "processing"
    / "stage_s_oracle_v1.json"
)
GENERATOR = FIXTURE.with_name("generate_stage_s_oracle.py")
SELECTION_GENERATOR = FIXTURE.with_name("generate_stage_s_selection_oracle.py")


def _load() -> dict[str, Any]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_golden_provenance_and_full_processing_inputs_are_independently_rehashed() -> None:
    golden = _load()
    assert golden["schema"] == "core-feature-processing-selection-oracle-v3"
    assert golden["dimensions"] == {
        "sessions": 260,
        "instruments": 24,
        "packages": 3,
        "input_record_count": 18_720,
        "processed_output_count": 18_720,
    }
    provenance = golden["provenance"]
    assert provenance["generator_version"] == "3.0.0"
    assert provenance["generator_sha256"] == hashlib.sha256(
        GENERATOR.read_bytes()
    ).hexdigest()
    assert provenance["selection_generator_sha256"] == hashlib.sha256(
        SELECTION_GENERATOR.read_bytes()
    ).hexdigest()
    assert provenance["selection_replays_hash"] == research_hash(
        golden["selection_replays"]
    )
    claimed = provenance["fixture_content_hash"]
    provenance["fixture_content_hash"] = None
    assert claimed == research_hash(golden)


def test_golden_proves_real_sw_l1_imputation_and_never_industry_fills_na() -> None:
    golden = _load()
    industries = {
        item["instrument_id"]: item["industry"] for item in golden["instruments"]
    }
    proof: tuple[int, float, float] | None = None
    for panel in golden["package_panels"]:
        for day in panel["days"]:
            states = day["inputs"]["states"]
            outputs = day["outputs"]
            for index, (state, source) in enumerate(
                zip(states, outputs["imputation_sources"], strict=True)
            ):
                if state == "not_applicable":
                    assert source == "u0_median"
                if state != "missing" or source != "sw_l1_median":
                    continue
                industry = industries[f"S{index:02d}"]
                peers = tuple(
                    position
                    for position, peer_state in enumerate(states)
                    if peer_state == "observed"
                    and industries[f"S{position:02d}"] == industry
                )
                all_observed = tuple(
                    position
                    for position, peer_state in enumerate(states)
                    if peer_state == "observed"
                )
                industry_median = float(
                    median(outputs["standardized_observed"][item] for item in peers)
                )
                u0_median = float(
                    median(outputs["standardized_observed"][item] for item in all_observed)
                )
                if industry_median != u0_median:
                    assert len(peers) >= 10
                    assert outputs["model_values"][index] == pytest.approx(
                        industry_median,
                        abs=1e-12,
                    )
                    proof = len(peers), industry_median, u0_median
                    break
            if proof is not None:
                break
        if proof is not None:
            break
    assert proof is not None


@pytest.mark.parametrize("replay_index", (0, 1))
def test_production_selection_matches_independent_h20_h60_replay(
    replay_index: int,
) -> None:
    replay = _load()["selection_replays"][replay_index]
    horizon = CoreLabelHorizon(replay["horizon"])
    parents, validated = production_validated_selection_case(
        ASTRAMIND_F0.package_id,
        horizon,
        profile="golden",
        fold_offset=replay["fold_offset"],
    )
    manifest = validated.manifest
    assert manifest == rebuild_core_feature_selection(parents)
    assert [item.isoformat() for item in manifest.fold.decision_dates] == replay[
        "decision_sessions"
    ]
    assert manifest.fold.fold_id == replay["independent_fold_identity"]
    assert list(manifest.selected_feature_keys) == replay["selected_feature_keys"]
    for actual, expected in zip(
        manifest.feature_evidence[:4],
        replay["feature_evidence"],
        strict=True,
    ):
        _assert_feature_evidence(actual, expected)
    assert manifest.feature_evidence[0].turnover == 0.0
    assert replay["feature_evidence"][2]["nonzero_valid_transitions"]
    assert {
        item["reason_code"]
        for item in replay["feature_evidence"][3]["invalid_transitions"]
    } == {
        "current_cross_section_insufficient",
        "previous_cross_section_insufficient",
    }
    assert [
        {
            "left_feature_key": item.left_feature_key,
            "right_feature_key": item.right_feature_key,
            "valid_date_count": item.valid_date_count,
            "median_daily_spearman": item.median_daily_spearman,
            "distance": item.distance,
        }
        for item in manifest.pair_correlations
    ] == replay["pair_correlations"]
    assert [
        {
            "members": list(item.members),
            "representative": item.representative,
        }
        for item in manifest.clusters
    ] == replay["clusters"]
    replay_body = {
        key: value
        for key, value in replay.items()
        if key not in {"replay_content_hash", "frozen_replay_identity"}
    }
    assert replay["replay_content_hash"] == research_hash(replay_body)
    assert replay["frozen_replay_identity"] == research_hash(
        {
            "schema": "core-stage-s-production-selection-replay-v1",
            "replay_content_hash": replay["replay_content_hash"],
        }
    )


def _assert_feature_evidence(actual: Any, expected: dict[str, Any]) -> None:
    daily = tuple(item.signed_rank_ic for item in actual.daily_rank_ic)
    transitions = tuple(
        item.model_dump(mode="json") for item in actual.turnover_transitions
    )
    assert actual.feature_key == expected["feature_key"]
    assert research_hash(daily) == expected["daily_signed_rankic_hash"]
    assert actual.signed_mean_rank_ic == pytest.approx(expected["signed_mean_rank_ic"])
    assert [item.valid_count for item in actual.subfolds] == expected[
        "subfold_valid_counts"
    ]
    assert actual.bootstrap_seed == expected["bootstrap_seed"]
    assert actual.bootstrap_p_value == expected["bootstrap_p_value"]
    assert actual.bh_rank == expected["bh_rank"]
    assert actual.bh_passed == expected["bh_passed"]
    assert actual.reason_code == expected["reason_code"]
    assert actual.turnover == expected["turnover"]
    assert actual.turnover_valid_transitions == expected[
        "turnover_valid_transitions"
    ]
    assert research_hash(transitions) == expected["turnover_transitions_hash"]
    assert [
        item
        for item in transitions
        if item["turnover_ratio"] not in {None, 0.0}
    ] == expected["nonzero_valid_transitions"]
    assert [item for item in transitions if not item["valid"]] == expected[
        "invalid_transitions"
    ]


def test_rankic_uses_observed_raw_state_not_adversarial_imputed_model_value() -> None:
    parents, validated = production_validated_selection_case(
        ASTRAMIND_F0.package_id,
        CoreLabelHorizon.H20,
        profile="golden",
    )
    feature_id = validated.manifest.feature_order[0]
    envelope = parents.processed_envelopes[30]
    rows = tuple(item for item in envelope.rows if item.feature_id == feature_id)
    missing = next(item for item in rows if item.instrument_id == "F")
    assert missing.is_missing and missing.model_value == -999.0
    evidence = validated.manifest.feature_evidence[0].daily_rank_ic[30]
    assert evidence.pair_count == 5
    assert evidence.rank_ic == 1.0
    labels = tuple(
        float(item.percentile)
        for item in parents.label_batches[30].rows
        if item.percentile is not None
    )
    all_model_values = tuple(float(item.model_value) for item in rows)
    assert spearman(all_model_values, labels) != evidence.rank_ic
