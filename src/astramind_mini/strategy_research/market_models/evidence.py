"""Freeze immutable market-model evidence identities."""

from __future__ import annotations

from datetime import datetime

from ..application.identity import research_hash
from .contracts import (
    DataGateState,
    EvidenceState,
    EvidenceWindow,
    MarketModelEvidenceBundle,
    ModelValidationSummary,
)


def freeze_evidence_bundle(
    *,
    manifest_id: str,
    windows: tuple[EvidenceWindow, ...],
    validations: tuple[ModelValidationSummary, ...],
    data_gates: tuple[DataGateState, ...],
    evidence_state: EvidenceState,
    created_at: datetime,
) -> MarketModelEvidenceBundle:
    provisional = MarketModelEvidenceBundle(
        evidence_bundle_id="market-model-evidence:pending",
        manifest_id=manifest_id,
        windows=windows,
        validations=validations,
        data_gates=data_gates,
        evidence_state=evidence_state,
        content_hash="sha256:" + "0" * 64,
        created_at=created_at,
    )
    digest = evidence_content_hash(provisional).removeprefix("sha256:")
    return provisional.model_copy(
        update={
            "evidence_bundle_id": f"market-model-evidence:{digest}",
            "content_hash": f"sha256:{digest}",
        }
    )


def evidence_content_hash(bundle: MarketModelEvidenceBundle) -> str:
    return research_hash(
        bundle.model_dump(
            mode="json",
            exclude={"evidence_bundle_id", "content_hash"},
        )
    )


__all__ = ["evidence_content_hash", "freeze_evidence_bundle"]
