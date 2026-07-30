"""Independent 10,000-replicate bootstrap oracle for Stage S."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import pytest

from astramind_mini.strategy_research.core.feature_selection import (
    centered_circular_block_bootstrap,
    selection_seed,
)

FIXTURE = Path(__file__).parents[1] / "fixtures" / "core" / "processing" / "stage_s_oracle_v1.json"
MASK64 = (1 << 64) - 1


def _load_bootstrap_oracle() -> dict[str, Any]:
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return fixture["oracle_vectors"]["bootstrap"]


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
        exceedances += resampled_mean / len(values) >= observed
    return exceedances, tuple(starts)


def test_bootstrap_matches_independent_10000_replicate_oracle() -> None:
    oracle = _load_bootstrap_oracle()
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
