"""Create a clearly synthetic formal-rotation fixture for browser acceptance."""

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from astramind_mini.market_regime.contracts import MarketRotationSnapshot
from astramind_mini.market_regime.domain.rotation import (
    IndustryCloseSeries,
    build_rotation_snapshot,
)
from astramind_mini.market_regime.public import FilesystemRotationStore, production_formula


def prepare(root: Path) -> MarketRotationSnapshot:
    calendar = tuple(date(2025, 1, 1) + timedelta(days=index) for index in range(141))
    industries = tuple(
        IndustryCloseSeries(
            industry_code=f"8010{index}0.SI",
            industry_name=f"合成行业{label}",
            closes={
                day: 100 * (1 + slope) ** offset * (1 + wave * ((offset + index) % 7))
                for offset, day in enumerate(calendar)
            },
            constituent_counts={day: 8 + index for day in calendar},
        )
        for index, (label, slope, wave) in enumerate(
            (
                ("甲", 0.0015, 0.0007),
                ("乙", 0.0004, -0.0005),
                ("丙", -0.0008, 0.0002),
                ("丁", -0.0002, -0.0006),
            ),
            start=1,
        )
    )
    snapshot = build_rotation_snapshot(
        data_snapshot_id="snapshot:sha256:" + "e" * 64,
        as_of=datetime(2025, 5, 21, tzinfo=UTC),
        created_at=datetime(2025, 5, 21, tzinfo=UTC),
        calendar=calendar,
        industries=industries,
        formula=production_formula(),
        known_gaps=("synthetic_e2e_fixture",),
    )
    FilesystemRotationStore(root).publish(snapshot)
    return snapshot


__all__ = ["prepare"]
