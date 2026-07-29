import math
from datetime import date, timedelta

import pytest

from astramind_mini.market_regime.domain.lifecycle import (
    IndustryIdentity,
    MembershipInterval,
    PriceObservation,
    StockStructure,
    build_industry_points,
    compute_stock_structures,
    confidence,
    lifecycle_stage,
)


@pytest.mark.parametrize(
    ("expected", "strong", "low", "delta_strong", "delta_low", "peak"),
    [
        ("明显退潮", 8, 48, -6, 6, 28),
        ("退潮观察", 14, 42, -3, 3, 22),
        ("强势扩散", 24, 20, 2, -1, 25),
        ("低位修复", 10, 44, 2, -6, 14),
        ("极端低位", 7, 58, 0, 0, 8),
        ("方向未明", 14, 36, 0, 0, 16),
    ],
)
def test_lifecycle_stage_uses_declared_priority(
    expected: str,
    strong: float,
    low: float,
    delta_strong: float,
    delta_low: float,
    peak: float,
) -> None:
    assert (
        lifecycle_stage(
            strong=strong,
            low=low,
            delta_strong=delta_strong,
            delta_low=delta_low,
            peak_strong=peak,
        )
        == expected
    )


def test_confidence_closes_low_coverage() -> None:
    assert confidence(0.75, 20) == "high"
    assert confidence(0.55, 10) == "medium"
    assert confidence(0.74, 9) == "low"


def test_stock_structure_calculation_is_deterministic_and_point_in_time() -> None:
    sessions = tuple(date(2025, 1, 1) + timedelta(days=index) for index in range(280))
    observations = tuple(
        PriceObservation(
            instrument_id=f"{instrument:06d}.SZ",
            trade_date=session,
            close=100
            * math.exp(
                0.001 * index + 0.018 * math.sin((index + instrument * 2) / 9) + instrument / 10_000
            ),
        )
        for instrument in range(24)
        for index, session in enumerate(sessions)
    )

    first = compute_stock_structures(
        observations,
        sessions[-25:],
        sessions=sessions,
    )
    second = compute_stock_structures(
        observations,
        sessions[-25:],
        sessions=sessions,
    )

    assert first == second
    assert set(first) == set(sessions[-25:])
    assert all(len(items) == 24 for items in first.values())


def test_industry_points_use_each_dates_effective_members_and_preserve_gaps() -> None:
    sessions = tuple(date(2026, 6, 1) + timedelta(days=index) for index in range(25))
    structures = {
        session: {
            "A.SZ": StockStructure(strong=index >= 18, low=index < 10),
            "B.SZ": StockStructure(strong=index >= 20, low=index < 12),
        }
        for index, session in enumerate(sessions)
    }
    points = build_industry_points(
        identities=(
            IndustryIdentity("I1", "行业一"),
            IndustryIdentity("I2", "无覆盖行业"),
        ),
        memberships=(
            MembershipInterval("A.SZ", "I1", sessions[0], sessions[15]),
            MembershipInterval("B.SZ", "I1", sessions[15], None),
        ),
        evaluation_dates=sessions,
        structures=structures,
        amount_shares={"I1": 0.4},
    )

    assert points[0].eligible_member_count == 1
    assert points[0].valid_member_count == 1
    assert len(points[0].trajectory) == 20
    assert points[0].amount_share_20d == 0.4
    assert points[1].strong_participation is None
    assert points[1].known_gaps == ("insufficient_price_history",)
