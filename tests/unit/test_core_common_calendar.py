from datetime import date

import pytest
from pydantic import ValidationError

from astramind_mini.strategy_research.core import (
    CORE_COMMON_CALENDAR_SEMANTICS,
    canonical_core_common_calendar_hash,
    freeze_core_common_calendar,
)

SESSIONS = tuple(date(2026, 1, day) for day in range(2, 31) if date(2026, 1, day).weekday() < 5)


def test_common_calendar_binds_id_semantics_and_every_session_position() -> None:
    calendar = freeze_core_common_calendar(
        calendar_id="sse-szse-common-v1",
        sessions=SESSIONS,
    )
    assert CORE_COMMON_CALENDAR_SEMANTICS == "core-common-calendar-v1"
    assert calendar.content_hash == canonical_core_common_calendar_hash(
        calendar_id=calendar.calendar_id,
        sessions=calendar.sessions,
    )
    for changed in (
        SESSIONS[:7] + SESSIONS[8:],
        (*SESSIONS[:7], date(2026, 1, 10), *SESSIONS[7:]),
        (*reversed(SESSIONS),),
    ):
        if tuple(sorted(changed)) != changed:
            with pytest.raises(ValidationError, match="unique and strictly ordered"):
                freeze_core_common_calendar(
                    calendar_id=calendar.calendar_id,
                    sessions=changed,
                )
        else:
            changed_calendar = freeze_core_common_calendar(
                calendar_id=calendar.calendar_id,
                sessions=changed,
            )
            assert changed_calendar.content_hash != calendar.content_hash


def test_calendar_rejects_stale_hash_through_validation_and_copy() -> None:
    calendar = freeze_core_common_calendar(
        calendar_id="sse-szse-common-v1",
        sessions=SESSIONS,
    )
    shortened = SESSIONS[:7] + SESSIONS[8:]
    payload = calendar.model_dump()
    payload["sessions"] = shortened
    with pytest.raises(ValidationError, match="content hash mismatch"):
        type(calendar).model_validate(payload)
    with pytest.raises(ValidationError, match="content hash mismatch"):
        calendar.model_copy(update={"sessions": shortened})
