import ast
import hashlib
import json
from copy import deepcopy
from datetime import date
from pathlib import Path

from astramind_mini.strategy_research.core.calendar import freeze_core_common_calendar
from astramind_mini.strategy_research.core.formulaic_alpha101.capabilities import (
    L3_CAPABILITY_MANIFEST_HASH,
    L3_CAPABILITY_STATUS,
    L3_CAPABILITY_VERSION,
    alpha101_l3_capability_manifest,
)
from astramind_mini.strategy_research.core.formulaic_alpha101.computation import (
    ALPHA101_COMPUTATION_MANIFEST_HASH,
    COMPUTATION_MANIFEST_VERSION,
    EXPRESSION_GRAMMAR_VERSION,
    INDUSTRY_MAPPING_VERSION,
    INPUT_MAPPING_VERSION,
    alpha101_computation_manifest,
    alpha101_computation_manifest_hash,
    canonical_computation_manifest_hash,
)
from astramind_mini.strategy_research.core.formulaic_alpha101.registry import (
    ALPHA101_DEFINITIONS,
    AUTHORITATIVE_SOURCE,
    EXPECTED_FORMULA_REGISTRY_HASH,
    FORMULA_REGISTRY_HASH,
    FORMULA_REGISTRY_VERSION,
    OPERATOR_SEMANTICS_VERSION,
    SOURCE_PDF_BYTES,
    SOURCE_PDF_SHA256,
)
from astramind_mini.strategy_research.core.packages import (
    FORMULAIC_ALPHA101,
    FORMULAIC_ALPHA101_FEATURE_ORDER,
)
from tests.fixtures.core.formulaic_alpha101.factory import (
    CALENDAR_FIXTURE,
    common_sessions,
    official_common_sessions,
)
from tests.fixtures.core.formulaic_alpha101.generate_golden import (
    CASES,
    GENERATOR_NAME,
    GENERATOR_VERSION,
    SOURCE_FILES,
    generate_case,
    generator_source_hash,
)


def test_registry_binds_the_v3_source_and_wp0070_public_identity() -> None:
    assert AUTHORITATIVE_SOURCE == "arxiv-1601.00991v3"
    assert SOURCE_PDF_BYTES == 244_416
    assert SOURCE_PDF_SHA256 == ("1f9c21afe32dcb3ee77b31548acdaea00451fbfa1c0ee10c907867bcc736fce9")
    assert FORMULA_REGISTRY_VERSION == "formulaic-alpha101-v3-registry-v1"
    assert OPERATOR_SEMANTICS_VERSION == "alpha101-operator-semantics-v1"
    assert FORMULA_REGISTRY_HASH == (
        "sha256:b2c9dcbeb8c81449cc2e60227aaf87da17a58bb51a04d0eca2468c594fa34a5c"
    )
    assert FORMULA_REGISTRY_HASH == EXPECTED_FORMULA_REGISTRY_HASH
    assert tuple(item.feature_definition_id for item in ALPHA101_DEFINITIONS) == (
        FORMULAIC_ALPHA101_FEATURE_ORDER
    )
    assert tuple(item.ordinal for item in ALPHA101_DEFINITIONS) == tuple(range(1, 102))
    assert {item.feature_definition_version for item in ALPHA101_DEFINITIONS} == {"1.0.0"}
    assert FORMULAIC_ALPHA101.required_definition_registry_hash == (
        "sha256:6895ebea945ed4c95e43d8fd7d19cd97a77fb3a32f7868133c320a5f9ebde1c5"
    )


def test_registry_preserves_raw_formula_tokens_ast_and_longest_history() -> None:
    alpha1 = ALPHA101_DEFINITIONS[0]
    assert "SignedPower" in alpha1.raw_formula
    assert "2." in alpha1.raw_decimal_tokens
    assert alpha1.canonical_ast[0] == "binary"
    assert max(item.maximum_history_sessions for item in ALPHA101_DEFINITIONS) == 252

    alpha58 = ALPHA101_DEFINITIONS[57]
    assert {"3.92795", "7.89291", "5.50322"} <= set(alpha58.raw_decimal_tokens)
    assert alpha58.maximum_history_sessions == 13
    assert ALPHA101_DEFINITIONS[100].raw_decimal_tokens[-1] == ".001"
    assert {
        name for item in ALPHA101_DEFINITIONS for name in item.inputs if name.startswith("adv")
    } == {
        "adv5",
        "adv10",
        "adv15",
        "adv20",
        "adv30",
        "adv40",
        "adv50",
        "adv60",
        "adv81",
        "adv120",
        "adv150",
        "adv180",
    }


def test_registry_keeps_paper_expressions_that_must_not_be_simplified() -> None:
    formulae = {item.ordinal: item.raw_formula for item in ALPHA101_DEFINITIONS}
    assert "close - delay(close, 7)" in formulae[19]
    assert "delta(close, 7)" in formulae[19]
    assert "close - 1" in formulae[29]
    assert "close - low" in formulae[53].split("/")[1]
    assert formulae[59].count("vwap *") == 2
    assert formulae[62].count("rank(open)") == 2
    assert formulae[66].count("low *") == 2
    assert "vwap + high" in formulae[77]
    assert formulae[82].count("open *") == 2
    assert formulae[89].count("low *") == 2
    assert formulae[100].lower().count("indneutralize") == 3
    assert "indneutralize(indneutralize(" in formulae[100].lower()
    assert formulae[101].endswith("+ .001))")
    assert "0.25 <" in formulae[46]
    assert "< (-1 * 0.1)" in formulae[49]
    assert "< (-1 * 0.05)" in formulae[51]


def test_all_eighteen_industry_formulas_have_the_strict_level_mapping() -> None:
    expected = {
        "sector": {58, 67, 76, 79, 82},
        "industry": {59, 63, 69, 70, 80, 87, 89, 91, 93, 97},
        "subindustry": {48, 67, 90, 100},
    }
    for level, ordinals in expected.items():
        assert {
            item.ordinal for item in ALPHA101_DEFINITIONS if level in item.industry_levels
        } == ordinals
    assert sum(bool(item.industry_levels) for item in ALPHA101_DEFINITIONS) == 18


def test_computation_manifest_binds_every_package_semantic_input() -> None:
    manifest = alpha101_computation_manifest()
    assert COMPUTATION_MANIFEST_VERSION == "formulaic-alpha101-computation-manifest-v1"
    assert ALPHA101_COMPUTATION_MANIFEST_HASH == (
        "sha256:26625f1b77bd63cc0064207e1612e2916ff99682aa4685807beeff3c735adc61"
    )
    assert alpha101_computation_manifest_hash() == ALPHA101_COMPUTATION_MANIFEST_HASH
    assert canonical_computation_manifest_hash(manifest) == (ALPHA101_COMPUTATION_MANIFEST_HASH)
    assert manifest["authoritative_source"] == AUTHORITATIVE_SOURCE
    assert manifest["source_pdf_sha256"] == SOURCE_PDF_SHA256
    assert manifest["operator_semantics_version"] == OPERATOR_SEMANTICS_VERSION
    assert manifest["expression_grammar_version"] == EXPRESSION_GRAMMAR_VERSION
    assert manifest["unary_power_precedence"] == (
        "power-before-prefix-unary; exponent-right-hand-side-accepts-unary"
    )
    assert manifest["pearson_two_point_rule"] == ("exact-delta-sign-with-zero-variance-failure")
    assert manifest["input_mapping_version"] == INPUT_MAPPING_VERSION
    assert manifest["input_slice_semantics"] == {
        "bars": "alpha101-daily-input-slice-v1",
        "industry": "alpha101-industry-input-slice-v1",
        "u0_history": "formulaic-alpha101-u0-history-v1",
    }
    assert manifest["industry_mapping_version"] == INDUSTRY_MAPPING_VERSION
    assert manifest["industry_fallback"] == "forbidden"
    assert manifest["l3_capability_manifest"] == alpha101_l3_capability_manifest()
    assert manifest["l3_capability_manifest_hash"] == L3_CAPABILITY_MANIFEST_HASH
    assert manifest["data_semantics_version"] == "core-data-semantics-v1"
    assert manifest["universe_version"] == "U0-v1"
    assert manifest["required_definition_registry_hash"] == (
        FORMULAIC_ALPHA101.required_definition_registry_hash
    )
    assert manifest["formula_registry_hash"] == FORMULA_REGISTRY_HASH
    assert manifest["industry_mapping"] == {
        "sector": [58, 67, 76, 79, 82],
        "industry": [59, 63, 69, 70, 80, 87, 89, 91, 93, 97],
        "subindustry": [48, 67, 90, 100],
    }
    definitions = manifest["definitions"]
    assert isinstance(definitions, list)
    assert len(definitions) == 101
    assert [item["ordinal"] for item in definitions] == list(range(1, 102))
    assert all(item["raw_formula"] and item["canonical_ast"] for item in definitions)


def test_old_semantics_or_formula_tampering_reidentifies_computation() -> None:
    manifest = alpha101_computation_manifest()
    old_semantics = deepcopy(manifest)
    old_semantics["operator_semantics_version"] = "alpha101-operator-semantics-v0"
    assert canonical_computation_manifest_hash(old_semantics) != (
        ALPHA101_COMPUTATION_MANIFEST_HASH
    )

    changed_formula = deepcopy(manifest)
    definitions = changed_formula["definitions"]
    assert isinstance(definitions, list)
    definitions[0]["raw_formula"] = "rank(close)"
    definitions[0]["canonical_ast"] = ["call", "rank", [["input", "close"]]]
    assert canonical_computation_manifest_hash(changed_formula) != (
        ALPHA101_COMPUTATION_MANIFEST_HASH
    )

    forged_capability = deepcopy(manifest)
    capability = forged_capability["l3_capability_manifest"]
    assert isinstance(capability, dict)
    capability["status"] = "available"
    capability["capability_version"] = "forged-l3-v999"
    assert canonical_computation_manifest_hash(forged_capability) != (
        ALPHA101_COMPUTATION_MANIFEST_HASH
    )


def test_l3_capability_is_explicitly_frozen_unavailable() -> None:
    manifest = alpha101_l3_capability_manifest()
    assert L3_CAPABILITY_STATUS == "unavailable"
    assert L3_CAPABILITY_VERSION == "sw2021-l3-unavailable-until-data-wp-v1"
    assert L3_CAPABILITY_MANIFEST_HASH == (
        "sha256:afce84df4dfc634b6b93fc371f5f68dc238dd921c3fc05f6a09f3964cf572c73"
    )
    assert manifest == {
        "manifest_version": "formulaic-alpha101-industry-capability-v1",
        "taxonomy": "SW2021",
        "level": "L3",
        "status": L3_CAPABILITY_STATUS,
        "capability_version": L3_CAPABILITY_VERSION,
        "activation_rule": "new-versioned-data-work-package-required",
        "string_presence_enables_capability": False,
    }
    forged = dict(manifest)
    forged["status"] = "available"
    assert canonical_computation_manifest_hash({"capability": forged}) != (
        canonical_computation_manifest_hash({"capability": manifest})
    )


def test_all_local_fixture_manifests_bind_the_same_source_and_semantics() -> None:
    fixture_dir = Path("tests/fixtures/core/formulaic_alpha101")
    for name in (
        "hand_operators",
        "full_260d",
        "edge_65d",
        "pit_industry",
    ):
        manifest = json.loads((fixture_dir / f"{name}.json").read_text(encoding="utf-8"))
        assert manifest["authoritative_source"] == AUTHORITATIVE_SOURCE
        assert manifest["source_pdf_sha256"] == SOURCE_PDF_SHA256
        assert manifest["formula_registry_version"] == FORMULA_REGISTRY_VERSION
        assert manifest["formula_registry_hash"] == FORMULA_REGISTRY_HASH
        assert manifest["operator_semantics_version"] == OPERATOR_SEMANTICS_VERSION
        assert manifest["computation_manifest_hash"] == ALPHA101_COMPUTATION_MANIFEST_HASH
        assert manifest["l3_capability_status"] == L3_CAPABILITY_STATUS
        assert manifest["l3_capability_version"] == L3_CAPABILITY_VERSION
        assert manifest["l3_capability_manifest_hash"] == L3_CAPABILITY_MANIFEST_HASH
        assert manifest["generator_name"]
        assert manifest["generator_version"]
        assert manifest["dependency_versions"]
        assert str(manifest["input_hash"]).startswith("sha256:")
        assert str(manifest["expected_output_hash"]).startswith("sha256:")
        if name in CASES:
            assert manifest["generator_name"] == GENERATOR_NAME
            assert manifest["generator_version"] == GENERATOR_VERSION
            assert manifest["generator_source_hash"] == generator_source_hash()


def test_official_common_calendar_provenance_excludes_exchange_holidays() -> None:
    sessions = official_common_sessions()
    specification = json.loads(CALENDAR_FIXTURE.read_text(encoding="utf-8"))
    calendar = freeze_core_common_calendar(
        calendar_id=specification["calendar_id"],
        sessions=sessions,
    )
    assert calendar.content_hash == specification["expected_calendar_content_hash"]
    holidays = {
        date(2025, 1, 28),
        date(2025, 2, 4),
        date(2025, 4, 4),
        date(2025, 5, 1),
        date(2025, 6, 2),
        date(2025, 10, 1),
        date(2025, 10, 8),
        date(2026, 1, 1),
        date(2026, 2, 16),
        date(2026, 2, 23),
        date(2026, 4, 6),
        date(2026, 5, 1),
        date(2026, 6, 19),
    }
    assert holidays.isdisjoint(sessions)
    assert all(day.weekday() < 5 for day in sessions)
    assert date(2025, 2, 5) in sessions
    assert date(2026, 2, 24) in sessions
    assert len(common_sessions(260)) == 260


def test_all_101_cell_goldens_are_frozen_and_have_zero_production_imports() -> None:
    fixture_dir = Path("tests/fixtures/core/formulaic_alpha101")
    for name in SOURCE_FILES:
        tree = ast.parse((fixture_dir / name).read_text(encoding="utf-8"))
        imported = {
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module is not None
        }
        imported.update(
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        )
        assert not {name for name in imported if name.startswith("astramind_mini")}
    oracle_parser = (fixture_dir / "oracle_runtime.py").read_text(encoding="utf-8")
    production_parser = Path(
        "src/astramind_mini/strategy_research/core/formulaic_alpha101/syntax.py"
    ).read_text(encoding="utf-8")
    assert "_PRECEDENCE" not in oracle_parser
    assert all(
        rule in oracle_parser
        for rule in (
            "def _conditional",
            "def _logical_or",
            "def _comparison",
            "def _additive",
            "def _multiplicative",
            "def _unary",
            "def _power",
        )
    )
    assert "_PRECEDENCE" in production_parser

    for case in CASES:
        golden = json.loads((fixture_dir / f"golden_{case}.json").read_text(encoding="utf-8"))
        cells = golden["cells"]
        encoded = json.dumps(cells, sort_keys=True, separators=(",", ":")).encode()
        assert golden["generator_source_hash"] == generator_source_hash()
        assert golden["production_imports"] == []
        assert golden["formula_count"] == 101
        assert golden["cell_count"] == 101 * golden["instrument_count"]
        assert {row[0] for row in cells} == set(FORMULAIC_ALPHA101_FEATURE_ORDER)
        assert golden["cells_content_hash"] == ("sha256:" + hashlib.sha256(encoded).hexdigest())
        coverage = golden["coverage"]
        assert (
            coverage["observed"] + coverage["missing"] + coverage["not_applicable"]
            == golden["cell_count"]
        )
        assert coverage["observed"] > 0
        assert coverage["missing"] > 0
        assert coverage["not_applicable"] > 0
    edge = json.loads((fixture_dir / "golden_edge_65d.json").read_text(encoding="utf-8"))
    assert edge["coverage"]["alpha101_nonfinite"] > 0


def test_independent_reference_executes_all_101_formulas_and_rebuilds_frozen_cells() -> None:
    fixture_dir = Path("tests/fixtures/core/formulaic_alpha101")
    formulae = json.loads(
        Path(
            "src/astramind_mini/strategy_research/core/formulaic_alpha101/formulae_v3.json"
        ).read_text(encoding="utf-8")
    )
    for case in CASES:
        frozen = json.loads((fixture_dir / f"golden_{case}.json").read_text(encoding="utf-8"))
        assert generate_case(case, formulae) == frozen


def test_full_golden_has_observed_evidence_for_every_non_l3_formula() -> None:
    fixture_dir = Path("tests/fixtures/core/formulaic_alpha101")
    golden = json.loads((fixture_dir / "golden_full_260d.json").read_text(encoding="utf-8"))
    formula_coverage = golden["formula_coverage"]
    l3_feature_ids = {f"alpha101_{ordinal:03d}" for ordinal in (48, 67, 90, 100)}
    assert set(formula_coverage) == set(FORMULAIC_ALPHA101_FEATURE_ORDER)
    for feature_id, coverage in formula_coverage.items():
        assert sum(coverage.values()) == golden["instrument_count"]
        if feature_id in l3_feature_ids:
            assert coverage["observed"] == 0
            assert coverage["not_applicable"] == golden["instrument_count"]
        else:
            assert coverage["observed"] >= 1
