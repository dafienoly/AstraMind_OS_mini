"""Canonical identity for the common SSE/SZSE session sequence."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from datetime import date
from typing import Any, Self

from pydantic import Field, model_validator

from astramind_mini.contracts.base import ContentHash, ContractModel, Identifier

CORE_COMMON_CALENDAR_SEMANTICS = "core-common-calendar-v1"


class CoreCommonCalendar(ContractModel):
    """One ordered, immutable common-session sequence shared by every core package."""

    calendar_id: Identifier
    sessions: tuple[date, ...] = Field(min_length=1)
    content_hash: ContentHash

    def model_copy(
        self,
        *,
        update: Mapping[str, Any] | None = None,
        deep: bool = False,
    ) -> Self:
        if not update:
            return super().model_copy(deep=deep)
        payload = self.model_dump()
        payload.update(update)
        return type(self).model_validate(payload)

    @model_validator(mode="after")
    def validate_identity(self) -> CoreCommonCalendar:
        if (
            len(set(self.sessions)) != len(self.sessions)
            or tuple(sorted(self.sessions)) != self.sessions
        ):
            raise ValueError("core common sessions must be unique and strictly ordered")
        expected = canonical_core_common_calendar_hash(
            calendar_id=self.calendar_id,
            sessions=self.sessions,
        )
        if self.content_hash != expected:
            raise ValueError("core common calendar content hash mismatch")
        return self


def canonical_core_common_calendar_hash(
    *,
    calendar_id: str,
    sessions: Sequence[date],
) -> str:
    payload = {
        "calendar_id": calendar_id,
        "calendar_semantics": CORE_COMMON_CALENDAR_SEMANTICS,
        "sessions": [item.isoformat() for item in sessions],
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def freeze_core_common_calendar(
    *,
    calendar_id: str,
    sessions: Sequence[date],
) -> CoreCommonCalendar:
    frozen_sessions = tuple(sessions)
    return CoreCommonCalendar(
        calendar_id=calendar_id,
        sessions=frozen_sessions,
        content_hash=canonical_core_common_calendar_hash(
            calendar_id=calendar_id,
            sessions=frozen_sessions,
        ),
    )


__all__ = [
    "CORE_COMMON_CALENDAR_SEMANTICS",
    "CoreCommonCalendar",
    "canonical_core_common_calendar_hash",
    "freeze_core_common_calendar",
]
