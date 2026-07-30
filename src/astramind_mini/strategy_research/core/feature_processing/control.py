"""Point-in-time control-plane contracts for core feature processing."""

from __future__ import annotations

import math
from collections.abc import Sequence
from datetime import date, datetime

from pydantic import Field, model_validator

from astramind_mini.contracts.base import (
    AwareDatetime,
    ContentHash,
    ContractModel,
    Identifier,
)

from ...application.identity import research_hash
from ..contracts import CoreUniverseDecision
from ..universe import core_universe_content_hash


class CoreProcessingControlRow(ContractModel):
    instrument_id: Identifier
    decision_date: date
    universe_decision: CoreUniverseDecision
    sw_l1: Identifier | None = None
    sw_l1_available_at: AwareDatetime | None = None
    float_market_cap: float | None = Field(default=None, gt=0.0)
    float_market_cap_available_at: AwareDatetime | None = None

    @model_validator(mode="after")
    def validate_control_pairs(self) -> CoreProcessingControlRow:
        if self.instrument_id != self.universe_decision.instrument_id:
            raise ValueError("control row instrument must match universe decision")
        if self.decision_date != self.universe_decision.decision_date:
            raise ValueError("control row date must match universe decision")
        if not self.universe_decision.research_member:
            raise ValueError("control panel contains research members only")
        if (self.sw_l1 is None) != (self.sw_l1_available_at is None):
            raise ValueError("industry value and availability must appear together")
        if (self.float_market_cap is None) != (self.float_market_cap_available_at is None):
            raise ValueError("market cap value and availability must appear together")
        if self.float_market_cap is not None and not math.isfinite(self.float_market_cap):
            raise ValueError("market cap control must be finite")
        return self


class CoreProcessingControlPanel(ContractModel):
    panel_id: Identifier
    content_hash: ContentHash
    decision_date: date
    input_cutoff: AwareDatetime
    universe_content_hash: ContentHash
    universe_rows: tuple[CoreUniverseDecision, ...] = Field(min_length=1)
    rows: tuple[CoreProcessingControlRow, ...] = Field(min_length=1)
    source_dataset_bindings: tuple[tuple[Identifier, ContentHash], ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_identity(self) -> CoreProcessingControlPanel:
        if self.rows != tuple(sorted(self.rows, key=lambda item: item.instrument_id)):
            raise ValueError("control rows must be ordered")
        if self.universe_rows != tuple(
            sorted(self.universe_rows, key=lambda item: item.instrument_id)
        ):
            raise ValueError("control universe audit rows must be ordered")
        if len({item.instrument_id for item in self.rows}) != len(self.rows):
            raise ValueError("control rows must be unique")
        if self.source_dataset_bindings != tuple(sorted(self.source_dataset_bindings)):
            raise ValueError("control dataset bindings must be ordered")
        if len({item[0] for item in self.source_dataset_bindings}) != len(
            self.source_dataset_bindings
        ):
            raise ValueError("control dataset bindings must be unique")
        if any(item.decision_date != self.decision_date for item in self.rows):
            raise ValueError("control rows must bind one decision date")
        if any(
            timestamp is not None and timestamp > self.input_cutoff
            for item in self.rows
            for timestamp in (
                item.sw_l1_available_at,
                item.float_market_cap_available_at,
            )
        ):
            raise ValueError("control observation crosses the decision cutoff")
        if core_universe_content_hash(self.universe_rows) != self.universe_content_hash:
            raise ValueError("control panel U0 hash mismatch")
        members = tuple(item for item in self.universe_rows if item.research_member)
        if tuple(item.universe_decision for item in self.rows) != members:
            raise ValueError("control rows must exactly embed research-member decisions")
        expected_hash = research_hash(_control_payload(self))
        expected_id = f"core-control-panel:{expected_hash.removeprefix('sha256:')}"
        if self.content_hash != expected_hash or self.panel_id != expected_id:
            raise ValueError("control panel canonical identity mismatch")
        return self

    @property
    def instrument_ids(self) -> tuple[str, ...]:
        return tuple(item.instrument_id for item in self.rows)


def build_core_processing_control_panel(
    *,
    decision_date: date,
    input_cutoff: datetime,
    universe_rows: Sequence[CoreUniverseDecision],
    rows: Sequence[CoreProcessingControlRow],
    source_dataset_bindings: Sequence[tuple[str, str]],
) -> CoreProcessingControlPanel:
    """Freeze controls after proving exact membership and point-in-time availability."""
    audit_rows = tuple(sorted(universe_rows, key=lambda item: item.instrument_id))
    if len({item.instrument_id for item in audit_rows}) != len(audit_rows):
        raise ValueError("control universe audit rows must be unique")
    decisions = tuple(item for item in audit_rows if item.research_member)
    ordered_rows = tuple(sorted(rows, key=lambda item: item.instrument_id))
    if tuple(item.instrument_id for item in ordered_rows) != tuple(
        item.instrument_id for item in decisions
    ):
        raise ValueError("control panel must exactly equal the research-member U0")
    if tuple(item.universe_decision for item in ordered_rows) != decisions:
        raise ValueError("control rows must embed the exact U0 decisions")
    universe_hash = core_universe_content_hash(audit_rows)
    bindings = tuple(sorted(source_dataset_bindings))
    payload = {
        "schema": "core-processing-control-panel-v1",
        "decision_date": decision_date,
        "input_cutoff": input_cutoff,
        "universe_content_hash": universe_hash,
        "universe_rows": audit_rows,
        "rows": ordered_rows,
        "source_dataset_bindings": bindings,
    }
    content_hash = research_hash(payload)
    return CoreProcessingControlPanel.model_validate(
        {
            "panel_id": f"core-control-panel:{content_hash.removeprefix('sha256:')}",
            "content_hash": content_hash,
            **{key: value for key, value in payload.items() if key != "schema"},
        }
    )


def _control_payload(panel: CoreProcessingControlPanel) -> dict[str, object]:
    return {
        "schema": "core-processing-control-panel-v1",
        "decision_date": panel.decision_date,
        "input_cutoff": panel.input_cutoff,
        "universe_content_hash": panel.universe_content_hash,
        "universe_rows": panel.universe_rows,
        "rows": panel.rows,
        "source_dataset_bindings": panel.source_dataset_bindings,
    }


__all__ = [
    "CoreProcessingControlPanel",
    "CoreProcessingControlRow",
    "build_core_processing_control_panel",
]
