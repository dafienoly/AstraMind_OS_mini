"""Read-only status projection for the five market model families."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from astramind_mini.contracts.base import (
    AwareDatetime,
    ContentHash,
    ContractModel,
    Identifier,
    Version,
)

ModelStatusState = Literal["active_v2", "unvalidated_v2", "fallback_v1", "blocked"]
ModelEvidenceState = Literal[
    "development_only",
    "unvalidated",
    "supported",
    "unsupported",
    "blocked",
]


class MarketModelStatusItem(ContractModel):
    model_family: Literal[
        "industry_heat",
        "industry_rotation",
        "industry_lifecycle",
        "industry_research_ranking",
        "etf_rotation",
    ]
    display_name: str
    state: ModelStatusState
    method_version: Version
    fallback_method_version: Version
    manifest_id: Identifier | None = None
    evidence_bundle_id: Identifier | None = None
    evidence_state: ModelEvidenceState
    effective_at: AwareDatetime | None = None
    reason_codes: tuple[Identifier, ...] = ()
    broker_actions_allowed: Literal[False] = False


class MarketModelStatusProjection(ContractModel):
    status_id: ContentHash
    as_of: AwareDatetime
    models: tuple[MarketModelStatusItem, ...] = Field(min_length=5, max_length=5)
    known_gaps: tuple[Identifier, ...] = ()
    broker_actions_allowed: Literal[False] = False


__all__ = [
    "MarketModelStatusItem",
    "MarketModelStatusProjection",
    "ModelEvidenceState",
    "ModelStatusState",
]
