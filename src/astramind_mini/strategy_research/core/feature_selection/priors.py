"""Runtime validation for the frozen Stage P selection prior."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from astramind_mini.contracts.base import ContentHash, ContractModel, Identifier

from ...application.identity import research_hash

STAGE_P_PRIORS_CONTENT_HASH = (
    "sha256:818554838477dd7ad9d3f4fc9490551cae0a78d69a315eb781fa62ed2a630952"
)
STAGE_P_TOKENIZER_RULES_HASH = (
    "sha256:7e2fa6eed8a0b668393f5b40ba65360b83d20f47742fd430bdbe7efa8b7aa3e4"
)
_PRIORS_PATH = Path(__file__).with_name("core_selection_priors_v1.json")


class CoreSelectionApplicability(ContractModel):
    scope: Identifier
    required_industry_levels: tuple[Identifier, ...]
    capability_status: Literal["available", "unavailable"]
    capability_note: str | None = None


class CoreSelectionPriorEntry(ContractModel):
    package_id: Identifier
    feature_key: Identifier = Field(alias="feature_id@definition_version")
    canonical_order: int = Field(gt=0)
    package_canonical_order: int = Field(gt=0)
    expected_direction: Literal[-1, 1]
    mechanism_id: Identifier
    mechanism_summary: str = Field(min_length=1)
    canonical_expression: str = Field(min_length=1)
    expression_hash: ContentHash
    complexity: int = Field(ge=1)
    applicability: CoreSelectionApplicability

    @property
    def feature_id(self) -> str:
        return self.feature_key.rsplit("@", 1)[0]

    @property
    def definition_version(self) -> str:
        return self.feature_key.rsplit("@", 1)[1]


class CoreSelectionPriorManifest(ContractModel):
    schema_name: Literal["core-selection-priors-v1"] = Field(alias="schema")
    stage: Literal["P"]
    prior_version: Literal["1.0.0"]
    authoritative_source_commit: Identifier
    direction_policy: Identifier
    stage_s_mutation_policy: str
    content_hash_policy: Identifier
    expression_hash_policy: Identifier
    source_policy: Identifier
    total_features: Literal[283]
    package_counts: dict[str, int]
    package_bindings: dict[str, dict[str, object]]
    tokenizer: dict[str, object]
    mechanism_vocabulary: tuple[dict[str, str], ...]
    entries: tuple[CoreSelectionPriorEntry, ...] = Field(min_length=283, max_length=283)
    priors_content_hash: ContentHash

    @model_validator(mode="after")
    def validate_frozen_identity(self) -> CoreSelectionPriorManifest:
        if self.priors_content_hash != STAGE_P_PRIORS_CONTENT_HASH:
            raise ValueError("Stage P prior hash is not the integrated frozen identity")
        if self.tokenizer.get("rules_hash") != STAGE_P_TOKENIZER_RULES_HASH:
            raise ValueError("Stage P tokenizer hash is not the integrated frozen identity")
        if len({item.feature_key for item in self.entries}) != 283:
            raise ValueError("selection prior definitions must be unique")
        if tuple(item.canonical_order for item in self.entries) != tuple(range(1, 284)):
            raise ValueError("selection prior canonical order mismatch")
        return self

    def package_entries(self, package_id: str) -> tuple[CoreSelectionPriorEntry, ...]:
        return tuple(item for item in self.entries if item.package_id == package_id)


@lru_cache(maxsize=1)
def load_core_selection_prior_manifest() -> CoreSelectionPriorManifest:
    """Load and independently re-hash the immutable Stage P JSON."""
    raw = _PRIORS_PATH.read_text(encoding="utf-8")
    document = json.loads(raw)
    if raw != json.dumps(document, ensure_ascii=False, sort_keys=True, indent=2) + "\n":
        raise ValueError("Stage P prior JSON is not canonical")
    claimed = document.pop("priors_content_hash")
    if claimed != STAGE_P_PRIORS_CONTENT_HASH or research_hash(document) != claimed:
        raise ValueError("Stage P prior canonical content hash mismatch")
    return CoreSelectionPriorManifest.model_validate_json(raw)


__all__ = [
    "STAGE_P_PRIORS_CONTENT_HASH",
    "STAGE_P_TOKENIZER_RULES_HASH",
    "CoreSelectionPriorEntry",
    "CoreSelectionPriorManifest",
    "load_core_selection_prior_manifest",
]
