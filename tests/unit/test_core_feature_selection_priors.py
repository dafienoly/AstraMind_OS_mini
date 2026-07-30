from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import cast

from astramind_mini.strategy_research.core.alpha158 import (
    ALPHA158_MANIFEST,
    EXPECTED_COMPUTATION_MANIFEST_HASH,
    QLIB_ALPHA158_FIELDS,
    QLIB_ALPHA158_NAMES,
)
from astramind_mini.strategy_research.core.f0 import (
    F0_DEFINITION_REGISTRY_HASH,
    F0_DEFINITIONS,
    F0_FULL_DEFINITION_MANIFEST_HASH,
)
from astramind_mini.strategy_research.core.formulaic_alpha101 import (
    ALPHA101_COMPUTATION_MANIFEST_HASH,
    ALPHA101_DEFINITIONS,
    FORMULA_REGISTRY_HASH,
    L3_CAPABILITY_MANIFEST_HASH,
)
from astramind_mini.strategy_research.core.packages import (
    ASTRAMIND_F0,
    FORMULAIC_ALPHA101,
    QLIB_ALPHA158,
)

PRIORS = Path(
    "src/astramind_mini/strategy_research/core/feature_selection/"
    "core_selection_priors_v1.json"
)
EXPECTED_PRIORS_CONTENT_HASH = (
    "sha256:818554838477dd7ad9d3f4fc9490551cae0a78d69a315eb781fa62ed2a630952"
)
EXPECTED_TOKENIZER_RULES_HASH = (
    "sha256:7e2fa6eed8a0b668393f5b40ba65360b83d20f47742fd430bdbe7efa8b7aa3e4"
)
EXPECTED_TOKENIZER = {
    "version": "core-selection-complexity-tokenizer-v1",
    "normalization": "exact_canonical_expression_utf8_no_casefold",
    "function_call_pattern": r"(?<![$\w.])([A-Za-z_][A-Za-z0-9_.]*)\s*(?=\()",
    "number_pattern": (
        r"(?<![A-Za-z0-9_.])(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?"
    ),
    "symbolic_operator_pattern": r"\*\*|>=|<=|==|!=|&&|\|\||[+\-*/^><?:]",
    "word_logical_pattern": r"\b(?:and|or|not)\b",
    "counting_rule": (
        "count each function-call identifier and each arithmetic, comparison, "
        "or logical operator occurrence once; rolling and lag calls are function "
        "tokens and are not double-counted"
    ),
    "excluded_tokens": [
        "variables",
        "parentheses",
        "numeric_constants",
        "commas",
    ],
}


def _sha256_text(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode()).hexdigest()


def _canonical_hash(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return _sha256_text(encoded)


def _complexity(expression: str, tokenizer: dict[str, object]) -> int:
    without_numbers = re.sub(str(tokenizer["number_pattern"]), " ", expression)
    calls = re.findall(str(tokenizer["function_call_pattern"]), without_numbers)
    symbols = re.findall(str(tokenizer["symbolic_operator_pattern"]), without_numbers)
    words = re.findall(
        str(tokenizer["word_logical_pattern"]),
        without_numbers,
        flags=re.IGNORECASE,
    )
    return len(calls) + len(symbols) + len(words)


def _source_definitions() -> list[tuple[str, str, str, dict[str, object]]]:
    definitions: list[tuple[str, str, str, dict[str, object]]] = [
        (
            ASTRAMIND_F0.package_id,
            f"{item.feature_definition_id}@{item.feature_definition_version}",
            item.formula,
            {
                "scope": item.applicability,
                "required_industry_levels": (
                    ["sw_l1"] if item.applicability == "strict_sw_l1" else []
                ),
                "capability_status": "available",
                "capability_note": None,
            },
        )
        for item in F0_DEFINITIONS
    ]
    definitions.extend(
        (
            QLIB_ALPHA158.package_id,
            f"{feature_id}@{ALPHA158_MANIFEST.definition_version}",
            expression,
            {
                "scope": "all_u0",
                "required_industry_levels": [],
                "capability_status": "available",
                "capability_note": None,
            },
        )
        for feature_id, expression in zip(
            QLIB_ALPHA158_NAMES,
            QLIB_ALPHA158_FIELDS,
            strict=True,
        )
    )
    definitions.extend(
        (
            FORMULAIC_ALPHA101.package_id,
            f"{item.feature_definition_id}@{item.feature_definition_version}",
            item.raw_formula,
            {
                "scope": (
                    "strict_point_in_time_industry_levels"
                    if item.industry_levels
                    else "all_u0"
                ),
                "required_industry_levels": list(item.industry_levels),
                "capability_status": (
                    "unavailable"
                    if "subindustry" in item.industry_levels
                    else "available"
                ),
                "capability_note": (
                    "当前申万三级点时能力不可用；公式保留方向和先验登记，计算时失败关闭。"
                    if "subindustry" in item.industry_levels
                    else None
                ),
            },
        )
        for item in ALPHA101_DEFINITIONS
    )
    return definitions


def _load() -> tuple[str, dict[str, object]]:
    raw = PRIORS.read_text(encoding="utf-8")
    return raw, json.loads(raw)


def test_prior_is_canonical_stage_p_and_bound_to_public_packages() -> None:
    raw, document = _load()
    assert raw == json.dumps(
        document,
        ensure_ascii=False,
        sort_keys=True,
        indent=2,
    ) + "\n"
    assert document["schema"] == "core-selection-priors-v1"
    assert document["stage"] == "P"
    assert document["prior_version"] == "1.0.0"
    assert document["authoritative_source_commit"] == (
        "27fb4113e7a7c7f92a94a5c90c5815852bd5bbe8"
    )
    assert document["direction_policy"] == (
        "ex_ante_formula_market_microstructure_and_accounting_hypotheses_only"
    )
    assert document["stage_s_mutation_policy"] == (
        "immutable; any change requires a new prior version and selection lineage"
    )
    assert document["total_features"] == 283
    assert document["package_counts"] == {
        ASTRAMIND_F0.package_id: 24,
        QLIB_ALPHA158.package_id: 158,
        FORMULAIC_ALPHA101.package_id: 101,
    }
    assert document["package_bindings"] == {
        ASTRAMIND_F0.package_id: {
            "canonical_dimension": 24,
            "computation_manifest_hash": F0_FULL_DEFINITION_MANIFEST_HASH,
            "definition_registry_hash": F0_DEFINITION_REGISTRY_HASH,
            "required_definition_registry_hash": (
                ASTRAMIND_F0.required_definition_registry_hash
            ),
        },
        QLIB_ALPHA158.package_id: {
            "canonical_dimension": 158,
            "computation_manifest_hash": EXPECTED_COMPUTATION_MANIFEST_HASH,
            "definition_registry_hash": (
                QLIB_ALPHA158.required_definition_registry_hash
            ),
            "expression_pairs_sha256": ALPHA158_MANIFEST.pairs_sha256,
            "required_definition_registry_hash": (
                QLIB_ALPHA158.required_definition_registry_hash
            ),
        },
        FORMULAIC_ALPHA101.package_id: {
            "canonical_dimension": 101,
            "computation_manifest_hash": ALPHA101_COMPUTATION_MANIFEST_HASH,
            "definition_registry_hash": FORMULA_REGISTRY_HASH,
            "l3_capability_manifest_hash": L3_CAPABILITY_MANIFEST_HASH,
            "required_definition_registry_hash": (
                FORMULAIC_ALPHA101.required_definition_registry_hash
            ),
        },
    }
    content_hash = document.pop("priors_content_hash")
    assert content_hash == EXPECTED_PRIORS_CONTENT_HASH
    assert content_hash == _canonical_hash(document)


def test_all_283_expressions_orders_hashes_and_complexities_recompute() -> None:
    _, document = _load()
    tokenizer = dict(cast(dict[str, object], document["tokenizer"]))
    rules_hash = tokenizer.pop("rules_hash")
    assert tokenizer == EXPECTED_TOKENIZER
    assert rules_hash == EXPECTED_TOKENIZER_RULES_HASH
    assert rules_hash == _canonical_hash(tokenizer)
    entries = document["entries"]
    assert isinstance(entries, list)
    sources = _source_definitions()
    assert len(entries) == len(sources) == 283
    assert len(
        {item["feature_id@definition_version"] for item in entries}
    ) == 283
    package_orders: dict[str, int] = {}
    for canonical_order, (entry, source) in enumerate(
        zip(entries, sources, strict=True),
        start=1,
    ):
        package_id, feature_key, expression, applicability = source
        package_orders[package_id] = package_orders.get(package_id, 0) + 1
        assert entry["package_id"] == package_id
        assert entry["feature_id@definition_version"] == feature_key
        assert entry["canonical_order"] == canonical_order
        assert entry["package_canonical_order"] == package_orders[package_id]
        assert entry["canonical_expression"] == expression
        assert entry["expression_hash"] == _sha256_text(expression)
        assert entry["complexity"] == _complexity(expression, tokenizer)
        assert entry["applicability"] == applicability


def test_direction_mechanism_and_l3_capability_are_complete_ex_ante_priors() -> None:
    _, document = _load()
    entries = document["entries"]
    assert isinstance(entries, list)
    vocabulary = document["mechanism_vocabulary"]
    assert isinstance(vocabulary, list)
    mechanism_ids = {item["mechanism_id"] for item in vocabulary}
    assert len(mechanism_ids) == len(vocabulary) == 31
    assert mechanism_ids == {item["mechanism_id"] for item in entries}
    assert Counter(item["expected_direction"] for item in entries) == {
        -1: 87,
        1: 196,
    }
    assert (
        min(item["complexity"] for item in entries),
        max(item["complexity"] for item in entries),
    ) == (1, 29)
    for mechanism in vocabulary:
        assert re.search(r"[\u4e00-\u9fff]", mechanism["name_zh"])
        assert re.search(r"[\u4e00-\u9fff]", mechanism["definition_zh"])
    forbidden = ("unknown", "待定", "经验上有效", "回测较好")
    l3_unavailable = []
    for entry in entries:
        assert entry["expected_direction"] in {-1, 1}
        assert entry["mechanism_id"] in mechanism_ids
        summary = entry["mechanism_summary"]
        assert isinstance(summary, str) and summary.strip()
        assert re.search(r"[\u4e00-\u9fff]", summary)
        assert not any(token in summary.lower() for token in forbidden)
        expected_phrase = (
            "预期方向为正"
            if entry["expected_direction"] == 1
            else "预期方向为负"
        )
        assert expected_phrase in summary
        applicability = entry["applicability"]
        assert applicability["scope"]
        assert applicability["capability_status"] in {"available", "unavailable"}
        if applicability["capability_status"] == "unavailable":
            l3_unavailable.append(entry["feature_id@definition_version"])
            assert "subindustry" in applicability["required_industry_levels"]
            assert "申万三级" in applicability["capability_note"]
    assert l3_unavailable == [
        "alpha101_048@1.0.0",
        "alpha101_067@1.0.0",
        "alpha101_090@1.0.0",
        "alpha101_100@1.0.0",
    ]
