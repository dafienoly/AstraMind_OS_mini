"""Dataset-level coverage, consistency, and performance replacement gates."""

from __future__ import annotations

from dataclasses import dataclass
from math import isclose
from statistics import quantiles

from ..contracts.source import BenchmarkSample, ProviderBatch


@dataclass(frozen=True, slots=True)
class QualityGateResult:
    dataset_name: str
    passed: bool
    expected_rows: int
    observed_rows: int
    duplicate_rows: int
    out_of_scope_rows: int
    value_mismatches: int
    known_gaps: tuple[str, ...]
    difference_details: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ReplacementDecision:
    dataset_name: str
    replace: bool
    miniqmt_p95_ms: float | None
    tushare_p95_ms: float | None
    throughput_ratio: float | None
    reasons: tuple[str, ...]


def aggregate_quality_results(
    dataset_name: str,
    values: tuple[QualityGateResult, ...],
) -> QualityGateResult:
    if not values:
        raise ValueError(f"missing_quality_gate:{dataset_name}")
    return QualityGateResult(
        dataset_name=dataset_name,
        passed=all(value.passed for value in values),
        expected_rows=sum(value.expected_rows for value in values),
        observed_rows=sum(value.observed_rows for value in values),
        duplicate_rows=sum(value.duplicate_rows for value in values),
        out_of_scope_rows=sum(value.out_of_scope_rows for value in values),
        value_mismatches=sum(value.value_mismatches for value in values),
        known_gaps=tuple(gap for value in values for gap in value.known_gaps),
        difference_details=tuple(detail for value in values for detail in value.difference_details)[
            :200
        ],
    )


def compare_provider_batches(
    *,
    dataset_name: str,
    candidate: ProviderBatch,
    reference: ProviderBatch,
    primary_key: tuple[str, ...],
    universe: frozenset[str] | None = None,
) -> QualityGateResult:
    candidate_rows = _by_key(candidate, primary_key)
    reference_rows = _by_key(reference, primary_key)
    duplicate_rows = len(candidate.rows) - len(candidate_rows)
    missing = set(reference_rows) - set(candidate_rows)
    extra = set(candidate_rows) - set(reference_rows)
    out_of_scope = 0
    if universe is not None:
        out_of_scope = sum(
            str(row.get("instrument_id") or row.get("ts_code")) not in universe
            for row in candidate.rows
        )
    difference_details = tuple(
        detail
        for key in sorted(set(candidate_rows) & set(reference_rows), key=str)
        for detail in _row_differences(
            dataset_name,
            key,
            candidate_rows[key],
            reference_rows[key],
        )
    )
    mismatched_keys = {detail.split(" field=", 1)[0] for detail in difference_details}
    mismatches = len(mismatched_keys)
    gaps = [
        *(f"missing_key:{key}" for key in sorted(missing, key=str)[:100]),
        *(f"extra_key:{key}" for key in sorted(extra, key=str)[:100]),
    ]
    if duplicate_rows:
        gaps.append(f"duplicate_primary_key:{duplicate_rows}")
    if out_of_scope:
        gaps.append(f"out_of_scope:{out_of_scope}")
    if mismatches:
        gaps.append(f"value_mismatch:{mismatches}")
    return QualityGateResult(
        dataset_name=dataset_name,
        passed=not gaps,
        expected_rows=len(reference_rows),
        observed_rows=len(candidate_rows),
        duplicate_rows=duplicate_rows,
        out_of_scope_rows=out_of_scope,
        value_mismatches=mismatches,
        known_gaps=tuple(gaps),
        difference_details=difference_details[:200],
    )


def replacement_decision(
    *,
    dataset_name: str,
    quality: QualityGateResult,
    samples: tuple[BenchmarkSample, ...],
) -> ReplacementDecision:
    scoped = [item for item in samples if item.dataset_name == dataset_name]
    mini = [item for item in scoped if item.provider_id == "miniqmt" and not item.error_code]
    tushare = [item for item in scoped if item.provider_id == "tushare" and not item.error_code]
    mini_p95 = _p95([item.total_ms for item in mini])
    tushare_p95 = _p95([item.total_ms for item in tushare])
    mini_rows_per_ms = _throughput(mini)
    tushare_rows_per_ms = _throughput(tushare)
    ratio = mini_rows_per_ms / tushare_rows_per_ms if tushare_rows_per_ms else None
    reasons = list(quality.known_gaps)
    scenario_ids = {item.scenario_id for item in scoped}
    for scenario_id in scenario_ids:
        scenario_mini = [item for item in mini if item.scenario_id == scenario_id]
        scenario_tushare = [item for item in tushare if item.scenario_id == scenario_id]
        scenario_mini_p95 = _p95([item.total_ms for item in scenario_mini])
        scenario_tushare_p95 = _p95([item.total_ms for item in scenario_tushare])
        scenario_ratio = _throughput_ratio(scenario_mini, scenario_tushare)
        if scenario_mini_p95 is None or scenario_tushare_p95 is None:
            reasons.append(f"benchmark_samples_insufficient:{scenario_id}")
        elif scenario_mini_p95 > scenario_tushare_p95 * 0.5:
            reasons.append(f"p95_not_twice_as_fast:{scenario_id}")
        if scenario_ratio is None or scenario_ratio < 2:
            reasons.append(f"throughput_not_twice_as_fast:{scenario_id}")
    if len(mini) != len([item for item in scoped if item.provider_id == "miniqmt"]):
        reasons.append("miniqmt_sample_errors")
    return ReplacementDecision(
        dataset_name=dataset_name,
        replace=quality.passed and not reasons,
        miniqmt_p95_ms=mini_p95,
        tushare_p95_ms=tushare_p95,
        throughput_ratio=ratio,
        reasons=tuple(reasons),
    )


def _by_key(
    batch: ProviderBatch,
    primary_key: tuple[str, ...],
) -> dict[tuple[object, ...], dict[str, object]]:
    return {tuple(row.get(field) for field in primary_key): row for row in batch.rows}


def _rows_equivalent(dataset: str, left: dict[str, object], right: dict[str, object]) -> bool:
    return not _row_differences(dataset, (), left, right)


def _row_differences(
    dataset: str,
    key: tuple[object, ...],
    left: dict[str, object],
    right: dict[str, object],
) -> tuple[str, ...]:
    ignored = {"provider", "retrieved_at", "available_at", "source_record_hash"}
    fields = set(right) - ignored
    differences = []
    for field in sorted(fields):
        a, b = left.get(field), right[field]
        if isinstance(a, int | float) and isinstance(b, int | float):
            tolerance = _tolerance(dataset, field, float(a), float(b))
            if not isclose(float(a), float(b), rel_tol=tolerance[0], abs_tol=tolerance[1]):
                differences.append(f"key={key!r} field={field} candidate={a!r} reference={b!r}")
        elif a != b:
            differences.append(f"key={key!r} field={field} candidate={a!r} reference={b!r}")
    return tuple(differences)


def _tolerance(dataset: str, field: str, left: float, right: float) -> tuple[float, float]:
    if field in {"open", "high", "low", "close", "pre_close", "previous_close"}:
        return 0, max(0.001, max(abs(left), abs(right)) * 0.0001)
    if field in {"volume", "vol", "amount", "volume_lots", "amount_cny"}:
        return 0.001, 0
    if dataset.startswith("financial") or dataset in {
        "shareholder_count",
        "top10_holder",
        "top10_float_holder",
    }:
        return 1e-8, 1.0
    return 1e-9, 1e-9


def _p95(values: list[float]) -> float | None:
    if len(values) < 2:
        return values[0] if values else None
    return quantiles(values, n=100, method="inclusive")[94]


def _throughput(samples: list[BenchmarkSample]) -> float:
    elapsed = sum(item.total_ms for item in samples)
    return sum(item.row_count for item in samples) / elapsed if elapsed else 0


def _throughput_ratio(
    candidate: list[BenchmarkSample],
    reference: list[BenchmarkSample],
) -> float | None:
    reference_rate = _throughput(reference)
    return _throughput(candidate) / reference_rate if reference_rate else None


__all__ = [
    "QualityGateResult",
    "ReplacementDecision",
    "aggregate_quality_results",
    "compare_provider_batches",
    "replacement_decision",
]
