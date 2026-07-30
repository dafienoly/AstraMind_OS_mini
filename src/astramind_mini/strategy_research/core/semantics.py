"""Point-in-time selectors governed by core-data-semantics-v1."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime, time
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import model_validator

from astramind_mini.contracts.base import (
    AwareDatetime,
    ContentHash,
    ContractModel,
    Identifier,
)

from .contracts import CoreDataSemantics, CoreInputLayer

SHANGHAI = ZoneInfo("Asia/Shanghai")
CORE_DATA_SEMANTICS = CoreDataSemantics()
IndustryLevel = Literal["sw_l1", "sw_l2", "sw_l3"]


class IndustryMembershipObservation(ContractModel):
    instrument_id: Identifier
    valid_from: date
    valid_to: date | None = None
    sw_l1: Identifier | None = None
    sw_l2: Identifier | None = None
    sw_l3: Identifier | None = None
    available_at: AwareDatetime
    source_record_hash: ContentHash

    @model_validator(mode="after")
    def validate_interval(self) -> IndustryMembershipObservation:
        if self.valid_to is not None and self.valid_from > self.valid_to:
            raise ValueError("industry membership interval is reversed")
        return self


class FinancialObservation(ContractModel):
    instrument_id: Identifier
    metric: Identifier
    report_period: date
    value: float
    revision_id: Identifier
    announced_at: AwareDatetime | None = None
    announcement_date: date | None = None
    source_record_hash: ContentHash

    @model_validator(mode="after")
    def validate_announcement(self) -> FinancialObservation:
        if (self.announced_at is None) == (self.announcement_date is None):
            raise ValueError("provide exactly one of announced_at or announcement_date")
        return self


class VisibleFinancialObservation(ContractModel):
    observation: FinancialObservation
    available_at: AwareDatetime


class CoreMarketObservation(ContractModel):
    instrument_id: Identifier
    market_date: date
    available_at: AwareDatetime
    input_layer: CoreInputLayer
    content_hash: ContentHash


def select_point_in_time_industry(
    observations: Sequence[IndustryMembershipObservation],
    *,
    instrument_id: str,
    decision_date: date,
    cutoff_at: datetime,
) -> IndustryMembershipObservation | None:
    """Return only the membership both effective and knowable at the cutoff."""
    visible = [
        item
        for item in observations
        if item.instrument_id == instrument_id
        and item.valid_from <= decision_date
        and (item.valid_to is None or item.valid_to >= decision_date)
        and item.available_at <= cutoff_at
    ]
    return max(visible, key=lambda item: (item.valid_from, item.available_at)) if visible else None


def point_in_time_industry_level(
    observation: IndustryMembershipObservation | None,
    *,
    level: IndustryLevel,
) -> str | None:
    """Return the exact requested SW2021 level without falling back upward."""
    return getattr(observation, level) if observation is not None else None


def financial_available_at(
    observation: FinancialObservation,
    *,
    common_sessions: Sequence[date],
) -> datetime | None:
    """Apply the conservative next-common-session close rule to date-only notices."""
    if observation.announced_at is not None:
        return observation.announced_at
    next_sessions = sorted(
        day for day in set(common_sessions) if day > observation.announcement_date  # type: ignore[operator]
    )
    if not next_sessions:
        return None
    return datetime.combine(next_sessions[0], time(15, 0), tzinfo=SHANGHAI)


def select_point_in_time_financial(
    observations: Sequence[FinancialObservation],
    *,
    instrument_id: str,
    metric: str,
    report_period: date,
    cutoff_at: datetime,
    common_sessions: Sequence[date],
) -> VisibleFinancialObservation | None:
    """Select the latest revision actually available by the historical cutoff."""
    visible: list[VisibleFinancialObservation] = []
    for item in observations:
        if (
            item.instrument_id != instrument_id
            or item.metric != metric
            or item.report_period != report_period
        ):
            continue
        available_at = financial_available_at(item, common_sessions=common_sessions)
        if available_at is not None and available_at <= cutoff_at:
            visible.append(
                VisibleFinancialObservation(observation=item, available_at=available_at)
            )
    return (
        max(visible, key=lambda item: (item.available_at, item.observation.revision_id))
        if visible
        else None
    )


def visible_core_market_observations(
    observations: Sequence[CoreMarketObservation],
    *,
    decision_date: date,
    cutoff_at: datetime,
) -> tuple[CoreMarketObservation, ...]:
    """Exclude future facts and every mutable/unsealed intraday layer."""
    allowed_layers = {
        CoreInputLayer.COMPLETED_DAILY,
        CoreInputLayer.SEALED_INTRADAY_DIAGNOSTIC,
    }
    return tuple(
        sorted(
            (
                item
                for item in observations
                if item.market_date <= decision_date
                and item.available_at <= cutoff_at
                and item.input_layer in allowed_layers
            ),
            key=lambda item: (item.market_date, item.instrument_id, item.content_hash),
        )
    )


__all__ = [
    "CORE_DATA_SEMANTICS",
    "CoreMarketObservation",
    "FinancialObservation",
    "IndustryLevel",
    "IndustryMembershipObservation",
    "VisibleFinancialObservation",
    "financial_available_at",
    "point_in_time_industry_level",
    "select_point_in_time_financial",
    "select_point_in_time_industry",
    "visible_core_market_observations",
]
