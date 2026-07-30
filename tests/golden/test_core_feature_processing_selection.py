from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

import pytest

from astramind_mini.strategy_research.core.feature_processing import (
    CoreCrossSectionStatus,
    CoreProcessingSpec,
    robust_cross_section,
)
from astramind_mini.strategy_research.core.feature_selection import (
    benjamini_hochberg,
    centered_circular_block_bootstrap,
    complete_linkage_clusters,
    selection_seed,
)
from astramind_mini.strategy_research.core.labels.builder import (
    average_rank_percentiles,
)
from astramind_mini.strategy_research.core.packages import (
    ASTRAMIND_F0,
    FORMULAIC_ALPHA101,
    QLIB_ALPHA158,
)

REPOSITORY = Path(__file__).parents[2]
FIXTURE = REPOSITORY / "tests" / "fixtures" / "core" / "processing" / "stage_s_oracle_v1.json"
MASK64 = (1 << 64) - 1


def _load_fixture() -> dict[str, Any]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _canonical_fixture_hash(fixture: dict[str, Any]) -> str:
    payload = json.loads(json.dumps(fixture))
    payload["provenance"]["fixture_content_hash"] = None
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return "sha256:" + hashlib.sha256(canonical).hexdigest()


def _splitmix64(state: int) -> tuple[int, int]:
    state = (state + 0x9E3779B97F4A7C15) & MASK64
    value = state
    value = ((value ^ (value >> 30)) * 0xBF58476D1CE4E5B9) & MASK64
    value = ((value ^ (value >> 27)) * 0x94D049BB133111EB) & MASK64
    return state, (value ^ (value >> 31)) & MASK64


def _independent_bootstrap(
    values: tuple[float, ...],
    *,
    seed: int,
    block_length: int,
    replicates: int,
) -> tuple[int, tuple[int, ...]]:
    observed = math.fsum(values) / len(values)
    centered = tuple(item - observed for item in values)
    blocks = math.ceil(len(values) / block_length)
    state = seed
    starts: list[int] = []
    exceedances = 0
    for _ in range(replicates):
        indices: list[int] = []
        for _ in range(blocks):
            state, output = _splitmix64(state)
            start = output % len(values)
            if len(starts) < 10:
                starts.append(start)
            indices.extend((start + offset) % len(values) for offset in range(block_length))
        resampled_mean = math.fsum(centered[index] for index in indices[: len(values)])
        if resampled_mean / len(values) >= observed:
            exceedances += 1
    return exceedances, tuple(starts)


def test_oracle_provenance_and_declared_260_by_24_by_3_panel_are_auditable() -> None:
    fixture = _load_fixture()
    provenance = fixture["provenance"]
    assert provenance["authoritative_source_commit"] == ("9e0c57fef5f916c3af4bd5fc8060c0a8ee1532a7")
    assert provenance["fixture_content_hash"] == _canonical_fixture_hash(fixture)
    panel = fixture["panel"]
    assert panel["package_ids"] == [
        ASTRAMIND_F0.package_id,
        QLIB_ALPHA158.package_id,
        FORMULAIC_ALPHA101.package_id,
    ]
    calendar_reference = panel["calendar_reference"]
    calendar_path = REPOSITORY / calendar_reference["path"]
    assert hashlib.sha256(calendar_path.read_bytes()).hexdigest() == (calendar_reference["sha256"])
    sessions = json.loads(calendar_path.read_text(encoding="utf-8"))[
        calendar_reference["json_field"]
    ]
    assert len(sessions) == calendar_reference["session_count"] == 260
    start_index = panel["instrument_generator"]["start_index"]
    instrument_count = panel["instrument_generator"]["count"]
    instruments = tuple(
        panel["instrument_generator"]["format"].format(index=index)
        for index in range(
            start_index,
            start_index + instrument_count,
        )
    )
    industries = tuple(
        panel["industry_generator"]["values"][index % len(panel["industry_generator"]["values"])]
        for index in range(len(instruments))
    )
    assert len(instruments) == 24
    assert set(industries) == {"IND-A", "IND-B", "IND-C"}
    assert len(panel["scenario_codes"]) == len(set(panel["scenario_codes"]))


def test_hand_oracles_cover_mad_rank_bh_and_complete_linkage() -> None:
    vectors = _load_fixture()["oracle_vectors"]
    zero_mad = vectors["zero_mad"]
    result = robust_cross_section(
        tuple(zero_mad["input"]),
        spec=CoreProcessingSpec(),
    )
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


def test_bootstrap_matches_independent_10000_replicate_oracle() -> None:
    oracle = _load_fixture()["oracle_vectors"]["bootstrap"]
    seed = selection_seed("F", "1.0.0", "H20", "fold-001")
    assert seed == oracle["seed"]
    base = tuple(
        math.sin(index * 0.37) + 0.35 * math.cos(index * 0.11) + (index % 7 - 3) * 0.03
        for index in range(oracle["sample_size"])
    )
    base_mean = math.fsum(base) / len(base)
    values = tuple(item - base_mean + oracle["mean_shift"] for item in base)
    exceedances, first_starts = _independent_bootstrap(
        values,
        seed=seed,
        block_length=oracle["block_length"],
        replicates=oracle["replicates"],
    )
    assert exceedances == oracle["exceedance_count"] == 376
    assert first_starts == tuple(oracle["first_ten_starts"])
    result = centered_circular_block_bootstrap(values, seed=seed)
    assert result.first_ten_starts == first_starts
    assert result.p_value == (oracle["p_value_numerator"] / oracle["p_value_denominator"])
    assert result.p_value == pytest.approx(377 / 10001, abs=0.0, rel=0.0)
