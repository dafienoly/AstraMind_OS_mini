"""Frozen point-in-time U0 history evidence, separate from current U0 identity."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime
from typing import Literal

from pydantic import Field, model_validator

from astramind_mini.contracts.base import (
    AwareDatetime,
    ContentHash,
    ContractModel,
    Identifier,
)

from ...application.identity import research_hash
from ..contracts import CoreUniverseDecision

HISTORY_MANIFEST_VERSION = "formulaic-alpha101-u0-history-v1"
HISTORY_DATASET_NAME = "formulaic_alpha101_u0_history"


class Alpha101UniverseHistoryManifest(ContractModel):
    manifest_version: Literal["formulaic-alpha101-u0-history-v1"] = (
        "formulaic-alpha101-u0-history-v1"
    )
    dataset_name: Identifier = HISTORY_DATASET_NAME
    universe_version: Literal["U0-v1"] = "U0-v1"
    history_content_hash: ContentHash
    common_sessions: tuple[date, ...] = Field(min_length=1)
    instruments: tuple[Identifier, ...] = Field(min_length=1)
    row_count: int = Field(gt=0)
    min_decision_date: date
    max_decision_date: date
    max_input_cutoff: AwareDatetime


class Alpha101UniverseHistory(ContractModel):
    manifest: Alpha101UniverseHistoryManifest
    decisions: tuple[CoreUniverseDecision, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_history(self) -> Alpha101UniverseHistory:
        sessions = self.manifest.common_sessions
        instruments = self.manifest.instruments
        if (
            len(set(sessions)) != len(sessions)
            or tuple(sorted(sessions)) != sessions
            or len(set(instruments)) != len(instruments)
        ):
            raise ValueError("U0 history axes must be unique and sessions ordered")
        expected_keys = {(day, instrument) for day in sessions for instrument in instruments}
        keys = {(item.decision_date, item.instrument_id) for item in self.decisions}
        if len(keys) != len(self.decisions) or keys != expected_keys:
            raise ValueError("U0 history must cover each common session-instrument exactly once")
        ordered = _ordered_decisions(sessions, instruments, self.decisions)
        if self.decisions != ordered:
            raise ValueError("U0 history decisions must use canonical axis order")
        if any(item.universe_version != self.manifest.universe_version for item in self.decisions):
            raise ValueError("U0 history decisions must use the frozen universe version")
        for day in sessions:
            cutoffs = {item.input_cutoff for item in self.decisions if item.decision_date == day}
            if len(cutoffs) != 1 or next(iter(cutoffs)).date() != day:
                raise ValueError("each U0 history day requires one explicit same-day cutoff")
        expected_hash = canonical_universe_history_hash(
            manifest_version=self.manifest.manifest_version,
            dataset_name=self.manifest.dataset_name,
            universe_version=self.manifest.universe_version,
            common_sessions=sessions,
            instruments=instruments,
            decisions=self.decisions,
        )
        if (
            self.manifest.row_count != len(self.decisions)
            or self.manifest.min_decision_date != sessions[0]
            or self.manifest.max_decision_date != sessions[-1]
            or self.manifest.max_input_cutoff != max(item.input_cutoff for item in self.decisions)
            or self.manifest.history_content_hash != expected_hash
        ):
            raise ValueError("U0 history content hash mismatch")
        return self

    @property
    def common_sessions(self) -> tuple[date, ...]:
        return self.manifest.common_sessions

    @property
    def instruments(self) -> tuple[Identifier, ...]:
        return self.manifest.instruments

    @property
    def history_content_hash(self) -> ContentHash:
        return self.manifest.history_content_hash

    def cutoff(self, session_index: int) -> datetime:
        day = self.common_sessions[session_index]
        return next(item.input_cutoff for item in self.decisions if item.decision_date == day)

    def members(self, session_index: int) -> tuple[bool, ...]:
        day = self.common_sessions[session_index]
        indexed = {
            item.instrument_id: item.research_member
            for item in self.decisions
            if item.decision_date == day
        }
        return tuple(indexed[instrument] for instrument in self.instruments)

    def current_decisions(self) -> tuple[CoreUniverseDecision, ...]:
        decision_date = self.common_sessions[-1]
        return tuple(item for item in self.decisions if item.decision_date == decision_date)


def canonical_universe_history_hash(
    *,
    manifest_version: str,
    dataset_name: str,
    universe_version: str,
    common_sessions: Sequence[date],
    instruments: Sequence[str],
    decisions: Sequence[CoreUniverseDecision],
) -> str:
    sessions = tuple(common_sessions)
    instrument_order = tuple(instruments)
    ordered = _ordered_decisions(sessions, instrument_order, decisions)
    return research_hash(
        {
            "manifest_version": manifest_version,
            "dataset_name": dataset_name,
            "universe_version": universe_version,
            "common_sessions": sessions,
            "instruments": instrument_order,
            "row_count": len(ordered),
            "min_decision_date": sessions[0],
            "max_decision_date": sessions[-1],
            "max_input_cutoff": max(item.input_cutoff for item in ordered),
            "decisions": ordered,
        }
    )


def freeze_alpha101_universe_history(
    *,
    common_sessions: Sequence[date],
    instruments: Sequence[str],
    decisions: Sequence[CoreUniverseDecision],
    dataset_name: str = HISTORY_DATASET_NAME,
) -> Alpha101UniverseHistory:
    sessions = tuple(common_sessions)
    instrument_order = tuple(instruments)
    ordered = _ordered_decisions(sessions, instrument_order, decisions)
    history_content_hash = canonical_universe_history_hash(
        manifest_version=HISTORY_MANIFEST_VERSION,
        dataset_name=dataset_name,
        universe_version="U0-v1",
        common_sessions=sessions,
        instruments=instrument_order,
        decisions=ordered,
    )
    return Alpha101UniverseHistory(
        manifest=Alpha101UniverseHistoryManifest(
            dataset_name=dataset_name,
            history_content_hash=history_content_hash,
            common_sessions=sessions,
            instruments=instrument_order,
            row_count=len(ordered),
            min_decision_date=sessions[0],
            max_decision_date=sessions[-1],
            max_input_cutoff=max(item.input_cutoff for item in ordered),
        ),
        decisions=ordered,
    )


def _ordered_decisions(
    common_sessions: Sequence[date],
    instruments: Sequence[str],
    decisions: Sequence[CoreUniverseDecision],
) -> tuple[CoreUniverseDecision, ...]:
    keyed = {(item.decision_date, item.instrument_id): item for item in decisions}
    if len(keyed) != len(decisions):
        raise ValueError("U0 history decisions cannot contain duplicate keys")
    expected = {(day, instrument) for day in common_sessions for instrument in instruments}
    if set(keyed) != expected:
        raise ValueError("U0 history decisions do not exactly cover the declared axes")
    ordered = tuple(
        keyed[(day, instrument)] for day in common_sessions for instrument in instruments
    )
    if tuple(decisions) != ordered:
        raise ValueError("U0 history decisions must use canonical axis order")
    return ordered


__all__ = [
    "HISTORY_DATASET_NAME",
    "HISTORY_MANIFEST_VERSION",
    "Alpha101UniverseHistory",
    "Alpha101UniverseHistoryManifest",
    "canonical_universe_history_hash",
    "freeze_alpha101_universe_history",
]
