"""Content identity for the exact Alpha101 input slices."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import TYPE_CHECKING

from ...application.identity import research_hash
from ..semantics import IndustryMembershipObservation

if TYPE_CHECKING:
    from .inputs import Alpha101DailyObservation

BAR_SLICE_SEMANTICS = "alpha101-daily-input-slice-v1"
INDUSTRY_SLICE_SEMANTICS = "alpha101-industry-input-slice-v1"


def canonical_alpha101_industries(
    industries: Sequence[IndustryMembershipObservation],
    instruments: tuple[str, ...],
) -> tuple[IndustryMembershipObservation, ...]:
    rows = tuple(industries)
    if any(item.instrument_id not in instruments for item in rows):
        raise ValueError("industry rows cannot include securities outside the panel")
    keys = {
        (
            item.instrument_id,
            item.valid_from,
            item.valid_to,
            item.available_at,
            item.source_record_hash,
        )
        for item in rows
    }
    if len(keys) != len(rows):
        raise ValueError("Alpha101 industry observations cannot be duplicated")
    return tuple(
        sorted(
            rows,
            key=lambda item: (
                item.instrument_id,
                item.valid_from,
                item.valid_to or date.max,
                item.available_at,
                item.source_record_hash,
            ),
        )
    )


def canonical_alpha101_bar_content_hash(
    *,
    sessions: Sequence[date],
    instruments: Sequence[str],
    observations: Sequence[Alpha101DailyObservation],
) -> str:
    ordered = tuple(sorted(observations, key=lambda item: (item.trade_date, item.instrument_id)))
    return research_hash(
        {
            "slice_semantics": BAR_SLICE_SEMANTICS,
            "sessions": tuple(sessions),
            "instruments": tuple(instruments),
            "observations": ordered,
        }
    )


def canonical_alpha101_industry_content_hash(
    *,
    sessions: Sequence[date],
    instruments: Sequence[str],
    industries: Sequence[IndustryMembershipObservation],
) -> str:
    ordered = tuple(
        sorted(
            industries,
            key=lambda item: (
                item.instrument_id,
                item.valid_from,
                item.valid_to or date.max,
                item.available_at,
                item.source_record_hash,
            ),
        )
    )
    return research_hash(
        {
            "slice_semantics": INDUSTRY_SLICE_SEMANTICS,
            "sessions": tuple(sessions),
            "instruments": tuple(instruments),
            "industries": ordered,
        }
    )


__all__ = [
    "BAR_SLICE_SEMANTICS",
    "INDUSTRY_SLICE_SEMANTICS",
    "canonical_alpha101_bar_content_hash",
    "canonical_alpha101_industries",
    "canonical_alpha101_industry_content_hash",
]
