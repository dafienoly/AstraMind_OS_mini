"""Strict evidence contracts for a read-only Paper startup handshake."""

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

from .account import AccountSnapshot


class BrokerAccountModeLock(ContractModel):
    mode_lock_id: Identifier
    configured_mode: Literal["simulation"]
    broker_account_matched: Literal[True]
    broker_account_type: int = Field(ge=0)
    broker_account_classification: int | None
    broker_account_status: int
    mode_evidence: Literal["configured_simulation_selector_matched"]
    known_gaps: tuple[Literal["account_classification_not_returned"], ...] = ()
    client_version: Version
    gateway_version: Version
    effective_mode: Literal["simulation"]
    broker_actions_allowed: Literal[False] = False
    verified_at: AwareDatetime
    content_hash: ContentHash


class ReadonlyCallbackHandshake(ContractModel):
    handshake_id: Identifier
    mode_lock_id: Identifier
    account_snapshot_id: Identifier
    status: Literal["ready", "quiet"]
    subscribed: Literal[True]
    unsubscribed: Literal[True]
    callback_types: tuple[
        Literal[
            "account_status",
            "asset",
            "position",
            "order",
            "trade",
            "disconnected",
        ],
        ...,
    ] = ()
    callback_count: int = Field(ge=0)
    foreign_account_callback_count: int = Field(ge=0)
    disconnected: bool
    started_at: AwareDatetime
    completed_at: AwareDatetime
    broker_actions_allowed: Literal[False] = False
    content_hash: ContentHash


class PaperAccountBaseline(ContractModel):
    baseline_id: Identifier
    mode_lock_id: Identifier
    handshake_id: Identifier
    account_snapshot_id: Identifier
    authority: Literal["complete_miniqmt_simulation_account"]
    inherited_instrument_ids: tuple[Identifier, ...]
    inherited_position_count: int = Field(ge=0)
    managed_position_count: Literal[0] = 0
    open_order_fingerprints: tuple[ContentHash, ...]
    startup_state: Literal["readonly_ready", "blocked"]
    blocker_codes: tuple[Identifier, ...]
    new_orders_frozen: Literal[True] = True
    broker_actions_allowed: Literal[False] = False
    created_at: AwareDatetime
    content_hash: ContentHash


class PaperStartupEvidence(ContractModel):
    mode_lock: BrokerAccountModeLock
    account_snapshot: AccountSnapshot
    callback_handshake: ReadonlyCallbackHandshake
    account_baseline: PaperAccountBaseline


__all__ = [
    "BrokerAccountModeLock",
    "PaperAccountBaseline",
    "PaperStartupEvidence",
    "ReadonlyCallbackHandshake",
]
