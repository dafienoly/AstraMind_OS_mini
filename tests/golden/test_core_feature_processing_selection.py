from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from astramind_mini.strategy_research.core.feature_processing import (
    CoreCrossSectionStatus,
    CoreProcessingSpec,
    robust_cross_section,
    state_aware_imputation_values,
)
from astramind_mini.strategy_research.core.feature_processing.control import (
    CoreProcessingControlRow,
)
from astramind_mini.strategy_research.core.feature_selection import (
    benjamini_hochberg,
    centered_circular_block_bootstrap,
    complete_linkage_clusters,
    selection_seed,
)
from astramind_mini.strategy_research.core.feature_values import (
    CoreFeatureValue,
    FeatureAvailabilityState,
)
from astramind_mini.strategy_research.core.labels import average_rank_percentiles
from astramind_mini.strategy_research.core.packages import (
    ASTRAMIND_F0,
    FORMULAIC_ALPHA101,
    QLIB_ALPHA158,
)

REPOSITORY = Path(__file__).parents[2]
FIXTURE = REPOSITORY / "tests" / "fixtures" / "core" / "processing" / "stage_s_oracle_v1.json"
GENERATOR = REPOSITORY / "tests" / "fixtures" / "core" / "processing" / "generate_stage_s_oracle.py"
SELECTION_GENERATOR = GENERATOR.with_name("generate_stage_s_selection_oracle.py")
INDEPENDENT_SELECTION = GENERATOR.with_name("stage_s_independent_selection.py")


def _load_fixture() -> dict[str, Any]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _canonical_hash(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _canonical_fixture_hash(fixture: dict[str, Any]) -> str:
    payload = json.loads(json.dumps(fixture))
    payload["provenance"]["fixture_content_hash"] = None
    return _canonical_hash(payload)


def test_oracle_provenance_hashes_and_actual_dimensions_are_auditable() -> None:
    fixture = _load_fixture()
    provenance = fixture["provenance"]
    assert fixture["schema"] == "core-feature-processing-selection-oracle-v4"
    assert provenance["generator_version"] == "4.0.0"
    assert provenance["authoritative_source_commit"] == ("9e0c57fef5f916c3af4bd5fc8060c0a8ee1532a7")
    assert provenance["generator_sha256"] == hashlib.sha256(GENERATOR.read_bytes()).hexdigest()
    assert (
        provenance["selection_generator_sha256"]
        == hashlib.sha256(SELECTION_GENERATOR.read_bytes()).hexdigest()
    )
    assert (
        provenance["independent_selection_sha256"]
        == hashlib.sha256(INDEPENDENT_SELECTION.read_bytes()).hexdigest()
    )
    assert provenance["fixture_content_hash"] == _canonical_fixture_hash(fixture)
    assert fixture["dimensions"] == {
        "sessions": 260,
        "instruments": 24,
        "packages": 3,
        "input_record_count": 18_720,
        "processed_output_count": 18_720,
    }
    calendar = fixture["calendar"]
    calendar_path = REPOSITORY / calendar["source_path"]
    assert calendar["source_sha256"] == hashlib.sha256(calendar_path.read_bytes()).hexdigest()
    assert len(calendar["sessions"]) == 260
    assert [item["package_id"] for item in fixture["package_panels"]] == [
        ASTRAMIND_F0.package_id,
        QLIB_ALPHA158.package_id,
        FORMULAIC_ALPHA101.package_id,
    ]
    assert all(
        len(panel["days"]) == 260
        and all(
            len(day["inputs"]["states"])
            == len(day["inputs"]["raw_values"])
            == len(day["outputs"]["model_values"])
            == 24
            for day in panel["days"]
        )
        for panel in fixture["package_panels"]
    )
    assert provenance["input_records_hash"] == _canonical_hash(
        [
            {
                "package_id": panel["package_id"],
                "days": [
                    {
                        "session": day["session"],
                        "inputs": day["inputs"],
                        "input_hash": day["input_hash"],
                    }
                    for day in panel["days"]
                ],
            }
            for panel in fixture["package_panels"]
        ]
    )
    assert provenance["processed_outputs_hash"] == _canonical_hash(
        [
            {
                "package_id": panel["package_id"],
                "days": [
                    {
                        "session": day["session"],
                        "statistics": day["statistics"],
                        "outputs": day["outputs"],
                        "output_hash": day["output_hash"],
                    }
                    for day in panel["days"]
                ],
            }
            for panel in fixture["package_panels"]
        ]
    )


def test_all_18720_processing_outputs_match_production_primitives() -> None:
    fixture = _load_fixture()
    instruments = fixture["instruments"]
    spec = CoreProcessingSpec()
    checked = 0
    for panel in fixture["package_panels"]:
        for day in panel["days"]:
            states = day["inputs"]["states"]
            raw_values = day["inputs"]["raw_values"]
            outputs = day["outputs"]
            observed_values = tuple(
                float(value)
                for state, value in zip(states, raw_values, strict=True)
                if state == "observed"
            )
            status, center, scale, lower, upper, winsorized, standardized = robust_cross_section(
                observed_values, spec=spec
            )
            statistics = day["statistics"]
            assert status.value == statistics["status"]
            assert center == pytest.approx(statistics["median_raw"], abs=1e-11)
            assert scale == pytest.approx(statistics["mad_scale"], abs=1e-11)
            assert lower == pytest.approx(statistics["winsor_lower"], abs=1e-11)
            assert upper == pytest.approx(statistics["winsor_upper"], abs=1e-11)
            observed_indexes = [index for index, state in enumerate(states) if state == "observed"]
            assert tuple(
                outputs["winsorized"][index] for index in observed_indexes
            ) == pytest.approx(winsorized, abs=1e-11)
            assert tuple(
                outputs["standardized_observed"][index] for index in observed_indexes
            ) == pytest.approx(standardized, abs=1e-11)
            _assert_imputation(day, instruments, spec)
            assert day["input_hash"] == _canonical_hash(day["inputs"])
            assert day["output_hash"] == _canonical_hash(
                {"statistics": statistics, "outputs": outputs}
            )
            checked += len(states)
    assert checked == 18_720


def _assert_imputation(
    day: dict[str, Any],
    instruments: list[dict[str, str]],
    spec: CoreProcessingSpec,
) -> None:
    decision_time = datetime.fromisoformat(day["session"]).replace(hour=16, tzinfo=UTC)
    states = day["inputs"]["states"]
    raw_values = day["inputs"]["raw_values"]
    raw_rows = tuple(
        CoreFeatureValue.model_construct(
            instrument_id=instrument["instrument_id"],
            availability_state=FeatureAvailabilityState(state),
            value_raw=value,
        )
        for instrument, state, value in zip(instruments, states, raw_values, strict=True)
    )
    controls = {
        instrument["instrument_id"]: CoreProcessingControlRow.model_construct(
            instrument_id=instrument["instrument_id"],
            decision_date=decision_time.date(),
            sw_l1=instrument["industry"],
        )
        for instrument in instruments
    }
    standardized = {
        instrument["instrument_id"]: float(day["outputs"]["standardized_observed"][index])
        for index, instrument in enumerate(instruments)
        if states[index] == "observed"
    }
    filled = state_aware_imputation_values(
        raw_rows,
        standardized_by_instrument=standardized,
        controls=controls,
        spec=spec,
    )
    for index, instrument in enumerate(instruments):
        if states[index] == "observed":
            continue
        value, source = filled[instrument["instrument_id"]]
        assert value == pytest.approx(day["outputs"]["model_values"][index], abs=1e-11)
        assert source.value == day["outputs"]["imputation_sources"][index]


def test_two_folds_two_production_selection_replays_and_three_seed_vectors_are_frozen() -> None:
    fixture = _load_fixture()
    replays = fixture["selection_replays"]
    assert len(replays) == 2
    assert [(item["fold_offset"], item["horizon"]) for item in replays] == [
        (0, "H20"),
        (1, "H60"),
    ]
    for replay in replays:
        assert len(replay["decision_sessions"]) == 180
        assert len(replay["feature_evidence"]) == 4
        assert replay["selected_feature_keys"]
        assert any(item["bh_passed"] for item in replay["feature_evidence"])
        assert any(not item["bh_passed"] for item in replay["feature_evidence"])
        payload = {
            key: value
            for key, value in replay.items()
            if key not in {"replay_content_hash", "frozen_replay_identity"}
        }
        assert replay["replay_content_hash"] == _canonical_hash(payload)
        assert replay["frozen_replay_identity"] == _canonical_hash(
            {
                "schema": "core-stage-s-production-selection-replay-v1",
                "replay_content_hash": replay["replay_content_hash"],
            }
        )
    assert fixture["provenance"]["selection_replays_hash"] == _canonical_hash(replays)

    vectors = fixture["bootstrap_vectors"]
    assert len(vectors) == 3
    for vector in vectors:
        feature_id, version = vector["feature_key"].rsplit("@", 1)
        seed = selection_seed(
            feature_id,
            version,
            vector["horizon"],
            vector["fold_id"],
        )
        assert seed == vector["seed"]
        result = centered_circular_block_bootstrap(
            tuple(0.1 for _ in range(180)),
            seed=seed,
        )
        assert list(result.first_ten_starts) == vector["first_ten_starts"]
        assert list(result.first_sample_indices) == vector["first_sample_indices"]


def test_hand_oracles_cover_mad_rank_bh_and_complete_linkage() -> None:
    vectors = _load_fixture()["oracle_vectors"]
    zero_mad = vectors["zero_mad"]
    result = robust_cross_section(tuple(zero_mad["input"]), spec=CoreProcessingSpec())
    assert result[0] == CoreCrossSectionStatus.ZERO_SCALE
    assert result[1] == zero_mad["median"]
    assert result[2] == zero_mad["mad_scale"]
    assert result[5] == tuple(zero_mad["winsorized"])
    assert result[6] == tuple(zero_mad["standardized"])

    rank = vectors["average_rank_percentile"]
    percentiles = average_rank_percentiles(tuple(zip(rank["ids"], rank["values"], strict=True)))
    assert [percentiles[item] for item in rank["ids"]] == rank["expected"]

    bh = vectors["benjamini_hochberg"]
    bh_result = benjamini_hochberg(bh["p_values_by_id"], fdr=bh["fdr"])
    assert [key for key, (_, _, passed) in bh_result.items() if passed] == bh["passed_ids"]

    linkage = vectors["complete_linkage"]
    distances = {
        frozenset(pair.split("|")): 1.0 - absolute_correlation
        for pair, absolute_correlation in linkage["absolute_correlations"].items()
    }
    clusters = complete_linkage_clusters(("C", "B", "A"), distances)
    assert clusters == tuple(tuple(item) for item in linkage["expected_clusters"])
