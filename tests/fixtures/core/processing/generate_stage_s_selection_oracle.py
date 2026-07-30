from __future__ import annotations

import hashlib
import json
import math
from itertools import pairwise
from statistics import median

from stage_s_independent_selection import replay_selection_decisions

MASK64 = (1 << 64) - 1


def _canonical_hash(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _average_ranks(values: tuple[float, ...]) -> tuple[float, ...]:
    ordered = sorted(enumerate(values), key=lambda item: (item[1], item[0]))
    ranks = [0.0] * len(values)
    start = 0
    while start < len(ordered):
        end = start + 1
        while end < len(ordered) and ordered[end][1] == ordered[start][1]:
            end += 1
        rank = (start + 1 + end) / 2.0
        for original, _ in ordered[start:end]:
            ranks[original] = rank
        start = end
    return tuple(ranks)


def _spearman(left: tuple[float, ...], right: tuple[float, ...]) -> float | None:
    if len(left) < 2:
        return None
    left_rank = _average_ranks(left)
    right_rank = _average_ranks(right)
    left_mean = math.fsum(left_rank) / len(left_rank)
    right_mean = math.fsum(right_rank) / len(right_rank)
    numerator = math.fsum(
        (left_value - left_mean) * (right_value - right_mean)
        for left_value, right_value in zip(left_rank, right_rank, strict=True)
    )
    denominator = math.sqrt(
        math.fsum((value - left_mean) ** 2 for value in left_rank)
        * math.fsum((value - right_mean) ** 2 for value in right_rank)
    )
    return numerator / denominator if denominator else None


def _profile(feature_index: int, day_index: int) -> tuple[float | None, ...]:
    ascending = (0.0, 1.0, 2.0, 3.0, 4.0, 5.0)
    if feature_index == 0:
        return (*ascending[:5], None) if day_index == 30 else ascending
    if feature_index == 1:
        return tuple(reversed(ascending))
    if feature_index == 2:
        if day_index == 30:
            return (*ascending[:5], None)
        return (0.0, 1.0, 2.0, 4.0, 3.0, 5.0) if day_index == 90 else ascending
    if feature_index == 3:
        return (0.0, None, None, None, None, None) if day_index == 60 else ascending
    return (None,) * 6


def _daily_rankic(
    horizon: str,
    feature_index: int,
    day_offset: int,
) -> tuple[float | None, ...]:
    labels = (
        tuple(float(index) for index in range(6))
        if horizon == "H20"
        else tuple(float(index) for index in reversed(range(6)))
    )
    values: list[float | None] = []
    for day in range(day_offset, day_offset + 180):
        profile = _profile(feature_index, day)
        observed = tuple(item for item in profile if item is not None)
        observed_labels = tuple(
            labels[index] for index, item in enumerate(profile) if item is not None
        )
        values.append(_spearman(observed, observed_labels))
    return tuple(values)


def _seed(feature_key: str, horizon: str, fold_id: str) -> int:
    payload = f"{feature_key}|{horizon}|{fold_id}".encode()
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "big")


def _splitmix64(state: int) -> tuple[int, int]:
    state = (state + 0x9E3779B97F4A7C15) & MASK64
    value = state
    value = ((value ^ (value >> 30)) * 0xBF58476D1CE4E5B9) & MASK64
    value = ((value ^ (value >> 27)) * 0x94D049BB133111EB) & MASK64
    return state, (value ^ (value >> 31)) & MASK64


def _bootstrap_p(values: tuple[float, ...], seed: int) -> float:
    observed = math.fsum(values) / len(values)
    centered = tuple(item - observed for item in values)
    state = seed
    exceedances = 0
    for _ in range(10_000):
        sampled: list[int] = []
        for _ in range(math.ceil(len(values) / 20)):
            state, output = _splitmix64(state)
            start = output % len(values)
            sampled.extend((start + offset) % len(values) for offset in range(20))
        mean = math.fsum(centered[index] for index in sampled[: len(values)]) / len(values)
        exceedances += mean >= observed
    return (exceedances + 1) / 10_001


def _turnover(
    feature_index: int,
    sessions: list[str],
    day_offset: int,
) -> tuple[float | None, list[dict[str, object]]]:
    daily = tuple(_profile(feature_index, day) for day in range(day_offset, day_offset + 180))
    transitions: list[dict[str, object]] = []
    valid_ratios: list[float] = []
    for index, (previous, current) in enumerate(pairwise(daily)):
        previous_ids = {position for position, value in enumerate(previous) if value is not None}
        current_ids = {position for position, value in enumerate(current) if value is not None}
        common = tuple(sorted(previous_ids & current_ids))
        reason = _turnover_reason(len(previous_ids), len(current_ids), len(common))
        ratio = None
        if reason == "available":
            previous_percentiles = _percentiles(previous)
            current_percentiles = _percentiles(current)
            ratio = math.fsum(
                abs(current_percentiles[item] - previous_percentiles[item]) for item in common
            ) / len(common)
            valid_ratios.append(ratio)
        transitions.append(
            {
                "previous_date": sessions[index],
                "current_date": sessions[index + 1],
                "previous_n_day": len(previous_ids),
                "current_n_day": len(current_ids),
                "n_common": len(common),
                "turnover_ratio": ratio,
                "valid": ratio is not None,
                "reason_code": reason,
            }
        )
    aggregate = float(median(valid_ratios)) if len(valid_ratios) >= 60 else None
    return aggregate, transitions


def _turnover_reason(previous: int, current: int, common: int) -> str:
    if previous < 2:
        return "previous_cross_section_insufficient"
    if current < 2:
        return "current_cross_section_insufficient"
    if common < 5:
        return "common_instruments_insufficient"
    return "available"


def _percentiles(values: tuple[float | None, ...]) -> dict[int, float]:
    observed = tuple(
        (index, float(value)) for index, value in enumerate(values) if value is not None
    )
    ranks = _average_ranks(tuple(value for _, value in observed))
    return {
        index: (rank - 1.0) / (len(observed) - 1)
        for (index, _), rank in zip(observed, ranks, strict=True)
    }


def _feature_summary(
    *,
    feature_key: str,
    horizon: str,
    feature_index: int,
    fold_id: str,
    sessions: list[str],
    day_offset: int,
) -> dict[str, object]:
    daily = _daily_rankic(horizon, feature_index, day_offset)
    valid = tuple(float(item) for item in daily if item is not None)
    subfold_counts = [
        sum(item is not None for item in daily[start : start + 60]) for start in (0, 60, 120)
    ]
    eligible = all(count >= 60 for count in subfold_counts)
    seed = _seed(feature_key, horizon, fold_id) if eligible else None
    p_value = _bootstrap_p(valid, seed) if seed is not None else None
    turnover, transitions = _turnover(feature_index, sessions, day_offset)
    coverage_daily = tuple(
        sum(item is not None for item in _profile(feature_index, day)) / 6.0
        for day in range(day_offset, day_offset + 180)
    )
    stability = (
        1.0 / (1.0 + float(median(abs(item - float(median(valid))) for item in valid)))
        if valid
        else None
    )
    direction_consistent = (
        all(
            math.fsum(float(item) for item in daily[start : start + 60] if item is not None)
            / subfold_counts[position]
            > 0.0
            for position, start in enumerate((0, 60, 120))
            if subfold_counts[position] >= 60
        )
        and eligible
    )
    return {
        "feature_key": feature_key,
        "daily_signed_rankic_hash": _canonical_hash(daily),
        "signed_mean_rank_ic": math.fsum(valid) / len(valid),
        "subfold_valid_counts": subfold_counts,
        "bootstrap_seed": seed,
        "bootstrap_p_value": p_value,
        "coverage_passed": sum(value >= 0.8 for value in coverage_daily) / 180 >= 0.9,
        "coverage_mean": math.fsum(coverage_daily) / len(coverage_daily),
        "subfold_sample_sufficient": eligible,
        "direction_consistent": direction_consistent,
        "selection_eligible": eligible and p_value is not None,
        "turnover": turnover,
        "turnover_valid_transitions": sum(item["valid"] for item in transitions),
        "turnover_transitions_hash": _canonical_hash(transitions),
        "stability": stability,
        "nonzero_valid_transitions": [
            item for item in transitions if item["turnover_ratio"] not in {None, 0.0}
        ],
        "invalid_transitions": [item for item in transitions if not item["valid"]],
    }


def build_selection_replays(
    sessions: list[str],
    prior: dict[str, object],
) -> list[dict[str, object]]:
    entries = [item for item in prior["entries"] if item["package_id"] == "astramind-f0-v1"][:4]
    return [
        _selection_replay(sessions, entries, horizon=horizon, offset=offset)
        for horizon, offset in (("H20", 0), ("H60", 1))
    ]


def _selection_replay(
    sessions: list[str],
    entries: list[dict[str, object]],
    *,
    horizon: str,
    offset: int,
) -> dict[str, object]:
    fold_sessions = sessions[offset : offset + 180]
    fold_identity = _fold_identity(fold_sessions, sessions[-1])
    evidence = [
        _feature_summary(
            feature_key=str(item["feature_id@definition_version"]),
            horizon=horizon,
            feature_index=index,
            fold_id=fold_identity,
            sessions=fold_sessions,
            day_offset=offset,
        )
        for index, item in enumerate(entries)
    ]
    profiles = [
        tuple(_profile(index, day) for day in range(offset, offset + 180))
        for index in range(len(entries))
    ]
    decisions = replay_selection_decisions(evidence, entries, profiles)
    payload = {
        "package_id": "astramind-f0-v1",
        "profile": "golden",
        "horizon": horizon,
        "fold_offset": offset,
        "decision_sessions": fold_sessions,
        "independent_fold_identity": fold_identity,
        **decisions,
    }
    payload["replay_content_hash"] = _canonical_hash(payload)
    payload["frozen_replay_identity"] = _canonical_hash(
        {
            "schema": "core-stage-s-production-selection-replay-v1",
            "replay_content_hash": payload["replay_content_hash"],
        }
    )
    return payload


def _fold_identity(fold_sessions: list[str], maturity_session: str) -> str:
    content_hash = _canonical_hash(
        {
            "schema": "core-selection-fold-v1",
            "decision_dates": fold_sessions,
            "label_maturity_cutoff": f"{maturity_session}T17:00:00+00:00",
            "subfolds": [
                {
                    "subfold_id": f"subfold-{index + 1}",
                    "decision_dates": fold_sessions[index * 60 : (index + 1) * 60],
                }
                for index in range(3)
            ],
        }
    )
    return f"core-selection-fold:{content_hash.removeprefix('sha256:')}"
