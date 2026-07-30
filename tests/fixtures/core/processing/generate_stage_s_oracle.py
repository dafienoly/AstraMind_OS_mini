"""Generate the stdlib-only independent Stage S processing/selection oracle."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from statistics import median

from generate_stage_s_selection_oracle import build_selection_replays

REPOSITORY = Path(__file__).parents[4]
OUTPUT = Path(__file__).with_name("stage_s_oracle_v1.json")
CALENDAR = REPOSITORY / "tests" / "fixtures" / "core" / "f0" / "golden_case.json"
PRIORS = REPOSITORY / Path(
    "src/astramind_mini/strategy_research/core/feature_selection/core_selection_priors_v1.json"
)
PACKAGES = (
    "astramind-f0-v1",
    "qlib-alpha158-79633dd",
    "formulaic-alpha101-v3",
)
MASK64 = (1 << 64) - 1


def _canonical_hash(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _round(value: float) -> float:
    return round(float(value), 12)


def _robust(values: list[float]) -> tuple[dict[str, object], list[float], list[float]]:
    center = float(median(values))
    scale = 1.4826 * float(median(abs(value - center) for value in values))
    if scale == 0.0:
        return (
            {
                "status": "zero_scale",
                "median_raw": center,
                "mad_scale": 0.0,
                "winsor_lower": center,
                "winsor_upper": center,
            },
            values,
            [0.0 for _ in values],
        )
    lower = center - 5.0 * scale
    upper = center + 5.0 * scale
    winsorized = [min(max(value, lower), upper) for value in values]
    standardized = [(value - center) / scale for value in winsorized]
    return (
        {
            "status": "ready",
            "median_raw": _round(center),
            "mad_scale": _round(scale),
            "winsor_lower": _round(lower),
            "winsor_upper": _round(upper),
        },
        winsorized,
        standardized,
    )


def _state(day: int, instrument: int, package: int) -> str:
    marker = day + instrument * 3 + package * 7
    if marker % 97 == 0:
        return "not_applicable"
    if marker % 23 == 0:
        return "missing"
    return "observed"


def _raw_value(day: int, instrument: int, package: int) -> float:
    return _round(
        package * 0.4
        + instrument * 0.17
        + math.sin((day + 1) * 0.071)
        + 0.2 * math.cos((day + instrument + 1) * 0.113)
    )


def _industry(instrument: int) -> str:
    if instrument < 11:
        return "IND-A"
    return "IND-B" if instrument < 22 else "IND-C"


def _day_record(package: int, day: int, session: str) -> dict[str, object]:
    input_rows = [
        {
            "instrument_id": f"S{instrument:02d}",
            "industry": _industry(instrument),
            "state": _state(day, instrument, package),
            "raw_value": (
                _raw_value(day, instrument, package)
                if _state(day, instrument, package) == "observed"
                else None
            ),
        }
        for instrument in range(24)
    ]
    observed = [item for item in input_rows if item["state"] == "observed"]
    statistics, winsorized, standardized = _robust([float(item["raw_value"]) for item in observed])
    standardized_by_id = {
        item["instrument_id"]: _round(value)
        for item, value in zip(observed, standardized, strict=True)
    }
    winsorized_by_id = {
        item["instrument_id"]: _round(value)
        for item, value in zip(observed, winsorized, strict=True)
    }
    u0_median = _round(float(median(standardized_by_id.values())))
    industry_values = {
        industry: [
            value
            for item_id, value in standardized_by_id.items()
            if next(item["industry"] for item in input_rows if item["instrument_id"] == item_id)
            == industry
        ]
        for industry in ("IND-A", "IND-B", "IND-C")
    }
    industry_medians = {
        industry: _round(float(median(values)))
        for industry, values in industry_values.items()
        if len(values) >= 10
    }
    output_rows = [
        _output_row(
            item,
            standardized_by_id,
            winsorized_by_id,
            industry_medians,
            u0_median,
        )
        for item in input_rows
    ]
    inputs = {
        "states": [item["state"] for item in input_rows],
        "raw_values": [item["raw_value"] for item in input_rows],
    }
    outputs = {
        "winsorized": [item["winsorized"] for item in output_rows],
        "standardized_observed": [item["standardized_observed"] for item in output_rows],
        "model_values": [item["model_value"] for item in output_rows],
        "imputation_sources": [item["imputation_source"] for item in output_rows],
        "missing_indicators": [item["is_missing"] for item in output_rows],
        "not_applicable_indicators": [item["is_not_applicable"] for item in output_rows],
    }
    return {
        "session": session,
        "inputs": inputs,
        "statistics": statistics,
        "outputs": outputs,
        "input_hash": _canonical_hash(inputs),
        "output_hash": _canonical_hash({"statistics": statistics, "outputs": outputs}),
    }


def _output_row(
    item: dict[str, object],
    standardized: dict[str, float],
    winsorized: dict[str, float],
    industry_medians: dict[str, float],
    u0_median: float,
) -> dict[str, object]:
    instrument = str(item["instrument_id"])
    state = str(item["state"])
    if state == "observed":
        return {
            "instrument_id": instrument,
            "winsorized": winsorized[instrument],
            "standardized_observed": standardized[instrument],
            "model_value": standardized[instrument],
            "imputation_source": "none",
            "is_missing": False,
            "is_not_applicable": False,
        }
    industry = str(item["industry"])
    use_industry = state == "missing" and industry in industry_medians
    return {
        "instrument_id": instrument,
        "winsorized": None,
        "standardized_observed": None,
        "model_value": industry_medians[industry] if use_industry else u0_median,
        "imputation_source": "sw_l1_median" if use_industry else "u0_median",
        "is_missing": state == "missing",
        "is_not_applicable": state == "not_applicable",
    }


def _seed(feature_key: str, horizon: str, fold: str) -> int:
    payload = f"{feature_key}|{horizon}|{fold}".encode()
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "big")


def _splitmix64(state: int) -> tuple[int, int]:
    state = (state + 0x9E3779B97F4A7C15) & MASK64
    value = state
    value = ((value ^ (value >> 30)) * 0xBF58476D1CE4E5B9) & MASK64
    value = ((value ^ (value >> 27)) * 0x94D049BB133111EB) & MASK64
    return state, (value ^ (value >> 31)) & MASK64


def _bootstrap_vector(feature_key: str, horizon: str, fold: str) -> dict[str, object]:
    seed = _seed(feature_key, horizon, fold)
    state = seed
    starts: list[int] = []
    for _ in range(10):
        state, output = _splitmix64(state)
        starts.append(output % 180)
    first_indices = [(start + offset) % 180 for start in starts[:9] for offset in range(20)]
    return {
        "feature_key": feature_key,
        "horizon": horizon,
        "fold_id": fold,
        "seed": seed,
        "first_ten_starts": starts,
        "first_sample_indices": first_indices,
    }


def _feature_keys(prior: dict[str, object]) -> dict[str, str]:
    entries = prior["entries"]
    if not isinstance(entries, list):
        raise ValueError("Stage P prior entries must be a list")
    return {
        package: next(
            str(item["feature_id@definition_version"])
            for item in entries
            if item["package_id"] == package
        )
        for package in PACKAGES
    }


def _package_panels(
    sessions: list[str],
    feature_keys: dict[str, str],
) -> list[dict[str, object]]:
    return [
        {
            "package_id": package,
            "feature_key": feature_keys[package],
            "days": [
                _day_record(package_index, day, session) for day, session in enumerate(sessions)
            ],
        }
        for package_index, package in enumerate(PACKAGES)
    ]


def _provenance(
    panels: list[dict[str, object]],
    replays: list[dict[str, object]],
) -> dict[str, object]:
    input_records = [
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
        for panel in panels
    ]
    processed_outputs = [
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
        for panel in panels
    ]
    return {
        "generator_identity": "tests/fixtures/core/processing/generate_stage_s_oracle.py",
        "generator_version": "3.0.0",
        "generation_policy": (
            "stdlib-only independent oracle; production evaluators are never imported"
        ),
        "authoritative_source_commit": "9e0c57fef5f916c3af4bd5fc8060c0a8ee1532a7",
        "generator_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "selection_generator_sha256": hashlib.sha256(
            Path(__file__).with_name(
                "generate_stage_s_selection_oracle.py"
            ).read_bytes()
        ).hexdigest(),
        "input_records_hash": _canonical_hash(input_records),
        "processed_outputs_hash": _canonical_hash(processed_outputs),
        "selection_replays_hash": _canonical_hash(replays),
        "fixture_content_hash": None,
    }


def _oracle_vectors() -> dict[str, object]:
    return {
        "zero_mad": {
            "input": [1.0, 1.0, 1.0, 100.0],
            "median": 1.0,
            "mad_scale": 0.0,
            "winsorized": [1.0, 1.0, 1.0, 100.0],
            "standardized": [0.0, 0.0, 0.0, 0.0],
        },
        "average_rank_percentile": {
            "ids": ["A", "B", "C"],
            "values": [0.2, 0.1, 0.1],
            "expected": [1.0, 0.25, 0.25],
        },
        "benjamini_hochberg": {
            "p_values_by_id": {"A": 0.02, "B": 0.02, "C": 0.074, "D": 0.2},
            "fdr": 0.1,
            "passed_ids": ["A", "B", "C"],
        },
        "complete_linkage": {
            "absolute_correlations": {"A|B": 0.9, "A|C": 0.8, "B|C": 0.9},
            "threshold": 0.85,
            "expected_clusters": [["A", "B"], ["C"]],
        },
        "bootstrap": {
            "seed_text": "F@1.0.0|H20|fold-001",
            "seed": 1290558554154497014,
            "sample_size": 180,
            "base_formula": "sin(i*0.37)+0.35*cos(i*0.11)+(i%7-3)*0.03",
            "mean_shift": 0.16561034216783938,
            "block_length": 20,
            "replicates": 10000,
            "first_ten_starts": [19, 127, 143, 153, 100, 162, 119, 51, 175, 73],
            "exceedance_count": 376,
            "p_value_numerator": 377,
            "p_value_denominator": 10001,
        },
    }


def _build_document(
    *,
    sessions: list[str],
    panels: list[dict[str, object]],
    replays: list[dict[str, object]],
    bootstrap_vectors: list[dict[str, object]],
) -> dict[str, object]:
    return {
        "schema": "core-feature-processing-selection-oracle-v3",
        "provenance": _provenance(panels, replays),
        "dimensions": {
            "sessions": 260,
            "instruments": 24,
            "packages": 3,
            "input_record_count": 260 * 24 * 3,
            "processed_output_count": 260 * 24 * 3,
        },
        "calendar": {
            "sessions": sessions,
            "source_path": str(CALENDAR.relative_to(REPOSITORY)),
            "source_sha256": hashlib.sha256(CALENDAR.read_bytes()).hexdigest(),
        },
        "instruments": [
            {"instrument_id": f"S{index:02d}", "industry": _industry(index)} for index in range(24)
        ],
        "package_panels": panels,
        "selection_replays": replays,
        "bootstrap_vectors": bootstrap_vectors,
        "oracle_vectors": _oracle_vectors(),
    }


def main() -> None:
    sessions = json.loads(CALENDAR.read_text(encoding="utf-8"))["common_sessions"]
    if len(sessions) != 260:
        raise ValueError("frozen calendar must contain exactly 260 sessions")
    prior = json.loads(PRIORS.read_text(encoding="utf-8"))
    feature_keys = _feature_keys(prior)
    panels = _package_panels(sessions, feature_keys)
    replays = build_selection_replays(sessions, prior)
    bootstrap_vectors = [
        _bootstrap_vector("F@1.0.0", "H20", "fold-001"),
        _bootstrap_vector(feature_keys[PACKAGES[1]], "H20", "fold-001"),
        _bootstrap_vector(feature_keys[PACKAGES[2]], "H60", "fold-002"),
    ]
    document = _build_document(
        sessions=sessions,
        panels=panels,
        replays=replays,
        bootstrap_vectors=bootstrap_vectors,
    )
    document["provenance"]["fixture_content_hash"] = _canonical_hash(document)
    OUTPUT.write_text(
        json.dumps(document, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
