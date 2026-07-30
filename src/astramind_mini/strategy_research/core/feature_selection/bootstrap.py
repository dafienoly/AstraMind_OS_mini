"""Exact SplitMix64 circular moving-block bootstrap."""

from __future__ import annotations

import hashlib
import math
from collections.abc import Sequence
from dataclasses import dataclass

_MASK = (1 << 64) - 1
_GAMMA = 0x9E3779B97F4A7C15
_MIX1 = 0xBF58476D1CE4E5B9
_MIX2 = 0x94D049BB133111EB


def selection_seed(
    feature_id: str,
    definition_version: str,
    horizon: str,
    fold_identity: str,
) -> int:
    payload = f"{feature_id}@{definition_version}|{horizon}|{fold_identity}".encode()
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "big", signed=False)


def splitmix64_next(state: int) -> tuple[int, int]:
    state = (state + _GAMMA) & _MASK
    value = state
    value = ((value ^ (value >> 30)) * _MIX1) & _MASK
    value = ((value ^ (value >> 27)) * _MIX2) & _MASK
    return state, (value ^ (value >> 31)) & _MASK


@dataclass(frozen=True)
class CoreBootstrapResult:
    seed: int
    sample_size: int
    block_length: int
    replicates: int
    observed_mean: float
    p_value: float
    first_ten_starts: tuple[int, ...]
    first_sample_indices: tuple[int, ...]


def centered_circular_block_bootstrap(
    values: Sequence[float],
    *,
    seed: int,
    block_length: int = 20,
    replicates: int = 10_000,
) -> CoreBootstrapResult:
    if not values or any(not math.isfinite(item) for item in values):
        raise ValueError("bootstrap requires a non-empty finite series")
    if block_length <= 0 or replicates <= 0:
        raise ValueError("bootstrap dimensions must be positive")
    sample = tuple(float(item) for item in values)
    observed_mean = math.fsum(sample) / len(sample)
    centered = tuple(item - observed_mean for item in sample)
    block_count = math.ceil(len(sample) / block_length)
    final_length = len(sample) - (block_count - 1) * block_length
    full_sums = tuple(
        math.fsum(centered[(start + offset) % len(sample)] for offset in range(block_length))
        for start in range(len(sample))
    )
    final_sums = tuple(
        math.fsum(centered[(start + offset) % len(sample)] for offset in range(final_length))
        for start in range(len(sample))
    )
    state = seed
    first_starts: list[int] = []
    first_indices: tuple[int, ...] = ()
    exceedances = 0
    for replicate in range(replicates):
        starts: list[int] = []
        for _ in range(block_count):
            state, output = splitmix64_next(state)
            starts.append(output % len(sample))
            if len(first_starts) < 10:
                first_starts.append(starts[-1])
        total = math.fsum(
            [
                *(full_sums[start] for start in starts[:-1]),
                final_sums[starts[-1]],
            ]
        )
        if total / len(sample) >= observed_mean:
            exceedances += 1
        if replicate == 0:
            first_indices = tuple(
                (start + offset) % len(sample)
                for block_index, start in enumerate(starts)
                for offset in range(
                    final_length if block_index == block_count - 1 else block_length
                )
            )
    return CoreBootstrapResult(
        seed=seed,
        sample_size=len(sample),
        block_length=block_length,
        replicates=replicates,
        observed_mean=observed_mean,
        p_value=(1 + exceedances) / (replicates + 1),
        first_ten_starts=tuple(first_starts),
        first_sample_indices=first_indices,
    )


__all__ = [
    "CoreBootstrapResult",
    "centered_circular_block_bootstrap",
    "selection_seed",
    "splitmix64_next",
]
