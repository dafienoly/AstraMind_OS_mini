from datetime import date, datetime

import pytest
from pydantic import ValidationError

from astramind_mini.strategy_research.core import (
    IndustryMembershipObservation,
    point_in_time_industry_level,
    select_point_in_time_industry,
)

TZ = datetime.fromisoformat("2026-01-01T00:00:00+08:00").tzinfo
CUTOFF = datetime(2026, 1, 30, 18, 0, tzinfo=TZ)
HASH_A = "sha256:" + ("a" * 64)
HASH_B = "sha256:" + ("b" * 64)


def test_future_industry_membership_is_excluded() -> None:
    old = IndustryMembershipObservation(
        instrument_id="600000.SH",
        valid_from=date(2025, 1, 1),
        sw_l1="bank",
        sw_l2="state_bank",
        sw_l3="large_bank",
        available_at=datetime(2025, 1, 2, 18, 0, tzinfo=TZ),
        source_record_hash=HASH_A,
    )
    future = IndustryMembershipObservation(
        instrument_id="600000.SH",
        valid_from=date(2026, 1, 1),
        sw_l1="non_bank",
        sw_l2="broker",
        sw_l3="broker",
        available_at=datetime(2026, 2, 2, 18, 0, tzinfo=TZ),
        source_record_hash=HASH_B,
    )

    selected = select_point_in_time_industry(
        (future, old),
        instrument_id="600000.SH",
        decision_date=date(2026, 1, 30),
        cutoff_at=CUTOFF,
    )

    assert selected == old
    l1_only = old.model_copy(update={"sw_l2": None, "sw_l3": None})
    assert point_in_time_industry_level(l1_only, level="sw_l2") is None


def test_industry_membership_uses_half_open_effective_interval() -> None:
    expired = IndustryMembershipObservation(
        instrument_id="600000.SH",
        valid_from=date(2026, 1, 1),
        valid_to=date(2026, 1, 2),
        sw_l1="expired-l1",
        available_at=datetime(2026, 1, 1, 18, 0, tzinfo=TZ),
        source_record_hash=HASH_A,
    )
    current = IndustryMembershipObservation(
        instrument_id="600000.SH",
        valid_from=date(2026, 1, 2),
        sw_l1="current-l1",
        available_at=datetime(2026, 1, 2, 9, 0, tzinfo=TZ),
        source_record_hash=HASH_B,
    )

    assert (
        select_point_in_time_industry(
            (expired,),
            instrument_id="600000.SH",
            decision_date=date(2026, 1, 2),
            cutoff_at=CUTOFF,
        )
        is None
    )
    assert (
        select_point_in_time_industry(
            (expired, current),
            instrument_id="600000.SH",
            decision_date=date(2026, 1, 2),
            cutoff_at=CUTOFF,
        )
        == current
    )


def test_empty_industry_membership_interval_is_rejected() -> None:
    with pytest.raises(ValidationError, match="non-empty and half-open"):
        IndustryMembershipObservation(
            instrument_id="600000.SH",
            valid_from=date(2026, 1, 2),
            valid_to=date(2026, 1, 2),
            sw_l1="empty",
            available_at=datetime(2026, 1, 2, 9, 0, tzinfo=TZ),
            source_record_hash=HASH_A,
        )
