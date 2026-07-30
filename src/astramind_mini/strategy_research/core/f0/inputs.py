"""Typed, point-in-time inputs owned by the astramind-f0-v1 package."""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Literal

from pydantic import Field, model_validator

from astramind_mini.contracts.base import (
    AwareDatetime,
    ContentHash,
    ContractModel,
    Identifier,
)

from ..contracts import CoreInputSnapshot, CoreUniverseDecision
from ..identity import validate_core_factor_sessions
from ..semantics import FinancialObservation, IndustryMembershipObservation
from ..universe import core_universe_content_hash


class F0CompanyType(StrEnum):
    CORPORATE = "corporate"
    BANK = "bank"
    INSURER = "insurer"
    BROKER = "broker"
    UNKNOWN = "unknown"


class F0FinancialMetric(StrEnum):
    PARENT_NET_PROFIT = "parent_net_profit"
    NET_PROFIT = "net_profit"
    REVENUE = "revenue"
    OPERATING_PROFIT = "operating_profit"
    OPERATING_CASH_FLOW = "operating_cash_flow"
    PARENT_EQUITY = "parent_equity"
    TOTAL_ASSETS = "total_assets"
    TOTAL_LIABILITIES = "total_liabilities"


class F0StatementKind(StrEnum):
    CUMULATIVE = "cumulative"
    INSTANT = "instant"


class F0FinancialFact(ContractModel):
    instrument_id: Identifier
    metric: F0FinancialMetric
    report_period: date
    statement_kind: F0StatementKind
    value: float
    comparable_scope: Identifier
    revision_id: Identifier
    announced_at: AwareDatetime | None = None
    announcement_date: date | None = None
    source_record_hash: ContentHash

    @model_validator(mode="after")
    def validate_announcement(self) -> F0FinancialFact:
        if (self.announced_at is None) == (self.announcement_date is None):
            raise ValueError("provide exactly one financial announcement time")
        return self

    def as_core_observation(self) -> FinancialObservation:
        return FinancialObservation(
            instrument_id=self.instrument_id,
            metric=self.metric.value,
            report_period=self.report_period,
            value=self.value,
            revision_id=self.revision_id,
            announced_at=self.announced_at,
            announcement_date=self.announcement_date,
            source_record_hash=self.source_record_hash,
        )


class F0DividendFact(ContractModel):
    instrument_id: Identifier
    event_id: Identifier
    revision_id: Identifier
    cash_dividend_per_share: float = Field(ge=0)
    implementation_basis_at: AwareDatetime
    announced_at: AwareDatetime | None = None
    announcement_date: date | None = None
    source_record_hash: ContentHash

    @model_validator(mode="after")
    def validate_announcement(self) -> F0DividendFact:
        if (self.announced_at is None) == (self.announcement_date is None):
            raise ValueError("provide exactly one dividend announcement time")
        return self

    def as_core_observation(self) -> FinancialObservation:
        return FinancialObservation(
            instrument_id=self.instrument_id,
            metric=f"cash_dividend_per_share:{self.event_id}",
            report_period=self.implementation_basis_at.date(),
            value=self.cash_dividend_per_share,
            revision_id=self.revision_id,
            announced_at=self.announced_at,
            announcement_date=self.announcement_date,
            source_record_hash=self.source_record_hash,
        )


class F0MarketBar(ContractModel):
    instrument_id: Identifier
    market_date: date
    available_at: AwareDatetime
    research_close: float | None = Field(default=None, gt=0)
    raw_close: float | None = Field(default=None, gt=0)
    amount_cny: float | None = Field(default=None, ge=0)
    turnover_rate: float | None = Field(default=None, ge=0)
    raw_total_market_cap_cny: float | None = Field(default=None, gt=0)
    trading_state: Literal["normal", "suspended", "price_limit"] = "normal"
    corporate_action_id: Identifier | None = None
    source_record_hash: ContentHash


class F0CompanyClassification(ContractModel):
    instrument_id: Identifier
    company_type: F0CompanyType
    effective_from: date
    effective_to: date | None = None
    available_at: AwareDatetime

    @model_validator(mode="after")
    def validate_interval(self) -> F0CompanyClassification:
        if self.effective_to is not None and self.effective_from > self.effective_to:
            raise ValueError("company classification interval is reversed")
        return self


class F0InputBundle(ContractModel):
    """Immutable observations evaluated against one CoreInputSnapshot cutoff."""

    core_input: CoreInputSnapshot
    common_sessions: tuple[date, ...] = Field(min_length=1)
    universe_decisions: tuple[CoreUniverseDecision, ...] = Field(min_length=1)
    market_bars: tuple[F0MarketBar, ...]
    financial_facts: tuple[F0FinancialFact, ...] = ()
    dividend_facts: tuple[F0DividendFact, ...] = ()
    industry_memberships: tuple[IndustryMembershipObservation, ...] = ()
    company_classifications: tuple[F0CompanyClassification, ...] = ()

    @model_validator(mode="after")
    def validate_identity_and_calendar(self) -> F0InputBundle:
        validate_f0_input_binding(self)
        return self


def validate_f0_input_binding(bundle: F0InputBundle) -> None:
    sessions = validate_core_factor_sessions(bundle.core_input, bundle.common_sessions)
    if bundle.core_input.decision_date not in sessions:
        raise ValueError("decision date must be a common session")
    _validate_unique_u0_decisions(bundle.universe_decisions)
    current = [
        item
        for item in bundle.universe_decisions
        if item.decision_date == bundle.core_input.decision_date
    ]
    if not current:
        raise ValueError("current U0 decision set is required")
    if core_universe_content_hash(current) != bundle.core_input.universe_content_hash:
        raise ValueError("current U0 content hash does not match CoreInputSnapshot")
    if any(item.input_cutoff > bundle.core_input.cutoff_at for item in current):
        raise ValueError("U0 input cutoff cannot exceed CoreInputSnapshot cutoff")
    canonical_financial_facts(bundle.financial_facts)
    canonical_dividend_facts(bundle.dividend_facts)


def _validate_unique_u0_decisions(
    decisions: tuple[CoreUniverseDecision, ...],
) -> None:
    identities = [(item.decision_date, item.instrument_id) for item in decisions]
    if len(identities) != len(set(identities)):
        raise ValueError("U0 decisions must be unique by decision date and instrument")


def canonical_financial_facts(
    facts: tuple[F0FinancialFact, ...],
) -> tuple[F0FinancialFact, ...]:
    """Reject conflicting stable revisions and deterministically deduplicate exact rows."""
    by_identity: dict[tuple[str, ...], F0FinancialFact] = {}
    for fact in facts:
        identity = (
            fact.instrument_id,
            fact.metric.value,
            fact.report_period.isoformat(),
            fact.statement_kind.value,
            fact.revision_id,
        )
        existing = by_identity.get(identity)
        if existing is not None and existing != fact:
            raise ValueError("conflicting financial facts share a stable revision identity")
        by_identity[identity] = fact
    return tuple(by_identity[identity] for identity in sorted(by_identity))


def canonical_dividend_facts(
    facts: tuple[F0DividendFact, ...],
) -> tuple[F0DividendFact, ...]:
    """Apply the same stable revision rule to dividend events."""
    by_identity: dict[tuple[str, ...], F0DividendFact] = {}
    for fact in facts:
        identity = (fact.instrument_id, fact.event_id, fact.revision_id)
        existing = by_identity.get(identity)
        if existing is not None and existing != fact:
            raise ValueError("conflicting dividend facts share a stable revision identity")
        by_identity[identity] = fact
    return tuple(by_identity[identity] for identity in sorted(by_identity))


def visible_market_bars(bundle: F0InputBundle) -> tuple[F0MarketBar, ...]:
    return tuple(
        item
        for item in bundle.market_bars
        if item.market_date <= bundle.core_input.decision_date
        and item.available_at <= bundle.core_input.cutoff_at
    )


def session_cutoff(day: date, final_cutoff: datetime) -> datetime:
    if day == final_cutoff.date():
        return final_cutoff
    return datetime.combine(day, final_cutoff.timetz())


__all__ = [
    "F0CompanyClassification",
    "F0CompanyType",
    "F0DividendFact",
    "F0FinancialFact",
    "F0FinancialMetric",
    "F0InputBundle",
    "F0MarketBar",
    "F0StatementKind",
    "canonical_dividend_facts",
    "canonical_financial_facts",
    "session_cutoff",
    "validate_f0_input_binding",
    "visible_market_bars",
]
