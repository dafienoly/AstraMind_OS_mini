"""Point-in-time eligibility rules for market-model samples."""

from __future__ import annotations

from typing import Literal

from pydantic import model_validator

from astramind_mini.contracts.base import AwareDatetime, ContractModel, Identifier

EvidencePurpose = Literal["development", "sealed_replay", "audit", "prospective"]
MembershipKnowledge = Literal["known_at_decision", "reconstructed_not_then_known"]


class PointInTimeSample(ContractModel):
    sample_id: Identifier
    entity_id: Identifier
    feature_at: AwareDatetime
    label_end_at: AwareDatetime
    label_available_at: AwareDatetime
    membership_knowledge: MembershipKnowledge
    known_gaps: tuple[Identifier, ...] = ()

    @model_validator(mode="after")
    def validate_times(self) -> PointInTimeSample:
        if self.feature_at >= self.label_end_at:
            raise ValueError("feature time must be before label end")
        if self.label_available_at < self.label_end_at:
            raise ValueError("label cannot be available before label end")
        return self


def sample_is_eligible(
    sample: PointInTimeSample,
    *,
    purpose: EvidencePurpose,
    evidence_cutoff: AwareDatetime,
) -> bool:
    if sample.label_available_at > evidence_cutoff:
        return False
    return not (
        purpose in {"sealed_replay", "audit", "prospective"}
        and sample.membership_knowledge == "reconstructed_not_then_known"
    )


def eligibility_reason(
    sample: PointInTimeSample,
    *,
    purpose: EvidencePurpose,
    evidence_cutoff: AwareDatetime,
) -> str | None:
    if sample.label_available_at > evidence_cutoff:
        return "label_not_mature"
    if (
        purpose in {"sealed_replay", "audit", "prospective"}
        and sample.membership_knowledge == "reconstructed_not_then_known"
    ):
        return "membership_reconstructed_not_then_known"
    return None


__all__ = [
    "EvidencePurpose",
    "MembershipKnowledge",
    "PointInTimeSample",
    "eligibility_reason",
    "sample_is_eligible",
]
