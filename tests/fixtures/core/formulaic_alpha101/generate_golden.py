"""One-time stdlib-only generator for frozen 101/101 Alpha101 expected cells."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from .oracle_evaluator import OracleEvaluator
from .oracle_panel import OraclePanel

GENERATOR_NAME = "standalone-stdlib-alpha101-golden"
GENERATOR_VERSION = "3.1.0"
GOLDEN_SCHEMA_VERSION = "formulaic-alpha101-cell-golden-v2"
FORMULAE_CONTENT_HASH = "sha256:f2bc4248676ef49e74a2c931109750a24096892502ae65d0d1cdd16ba306df44"
FORMULA_REGISTRY_HASH = "sha256:b2c9dcbeb8c81449cc2e60227aaf87da17a58bb51a04d0eca2468c594fa34a5c"
COMPUTATION_MANIFEST_HASH = (
    "sha256:26625f1b77bd63cc0064207e1612e2916ff99682aa4685807beeff3c735adc61"
)
L3_CAPABILITY_MANIFEST_HASH = (
    "sha256:afce84df4dfc634b6b93fc371f5f68dc238dd921c3fc05f6a09f3964cf572c73"
)
SOURCE_FILES = (
    "generate_golden.py",
    "oracle_evaluator.py",
    "oracle_panel.py",
    "oracle_runtime.py",
)
CASES = ("full_260d", "edge_65d", "pit_industry")


def generator_source_hash() -> str:
    digest = hashlib.sha256()
    root = Path(__file__).parent
    for name in SOURCE_FILES:
        digest.update(name.encode())
        digest.update(b"\0")
        digest.update((root / name).read_bytes())
    return "sha256:" + digest.hexdigest()


def generate_case(case: str, formulae: list[str]) -> dict[str, Any]:
    panel = OraclePanel(case)
    evaluator = OracleEvaluator(panel)
    final = panel.session_count - 1
    cells = []
    coverage: Counter[str] = Counter()
    formula_coverage: dict[str, dict[str, int]] = {}
    for ordinal, formula in enumerate(formulae, start=1):
        feature_id = f"alpha101_{ordinal:03d}"
        states: Counter[str] = Counter()
        for instrument_index, instrument in enumerate(panel.instruments):
            cell = evaluator.evaluate(
                formula,
                session=final,
                instrument=instrument_index,
            )
            cells.append([feature_id, instrument, *cell.frozen()])
            coverage[cell.state] += 1
            states[cell.state] += 1
            if cell.reason is not None:
                coverage[cell.reason] += 1
        formula_coverage[feature_id] = {
            state: states[state] for state in ("observed", "missing", "not_applicable")
        }
    cells_hash = _json_hash(cells)
    return {
        "schema_version": GOLDEN_SCHEMA_VERSION,
        "case": case,
        "authoritative_source": "arxiv-1601.00991v3",
        "source_pdf_sha256": ("1f9c21afe32dcb3ee77b31548acdaea00451fbfa1c0ee10c907867bcc736fce9"),
        "formula_registry_version": "formulaic-alpha101-v3-registry-v1",
        "formula_registry_hash": FORMULA_REGISTRY_HASH,
        "formulae_content_hash": FORMULAE_CONTENT_HASH,
        "operator_semantics_version": "alpha101-operator-semantics-v1",
        "computation_manifest_hash": COMPUTATION_MANIFEST_HASH,
        "l3_capability_status": "unavailable",
        "l3_capability_version": "sw2021-l3-unavailable-until-data-wp-v1",
        "l3_capability_manifest_hash": L3_CAPABILITY_MANIFEST_HASH,
        "generator_name": GENERATOR_NAME,
        "generator_version": GENERATOR_VERSION,
        "generator_source_hash": generator_source_hash(),
        "dependency_versions": ["python-stdlib-only"],
        "production_imports": [],
        "method": (
            "Grammar-ladder parser, standalone synthetic input mapper, scalar operators "
            "and cell evaluator; no production parser, input mapper, operator or evaluator "
            "is imported."
        ),
        "formula_count": len(formulae),
        "instrument_count": len(panel.instruments),
        "cell_count": len(cells),
        "oracle_input_hash": panel.input_content_hash(),
        "input_boundary_expectations": {
            "finite": "accepted",
            "nan": "rejected",
            "positive_inf": "rejected",
            "negative_inf": "rejected",
        },
        "coverage": dict(sorted(coverage.items())),
        "formula_coverage": formula_coverage,
        "cells_content_hash": cells_hash,
        "cells": cells,
    }


def _json_hash(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("formulae", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    arguments = parser.parse_args()
    formulae = json.loads(arguments.formulae.read_text(encoding="utf-8"))
    if len(formulae) != 101 or _json_hash(formulae) != FORMULAE_CONTENT_HASH:
        raise ValueError("generator requires the audited v3 101-formula source")
    for case in CASES:
        payload = generate_case(case, formulae)
        target = arguments.output_dir / f"golden_{case}.json"
        target.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
