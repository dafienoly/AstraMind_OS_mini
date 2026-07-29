import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from astramind_mini.market_regime.adapters import FilesystemRotationStore
from astramind_mini.market_regime.application import production_formula
from astramind_mini.market_regime.contracts import MarketRotationSnapshot
from astramind_mini.market_regime.domain.identity import content_hash
from astramind_mini.market_regime.domain.rotation import (
    DISPLAY_TRANSFORM_VERSION,
    IndustryCloseSeries,
    build_rotation_snapshot,
)


def _inputs(days: int = 141) -> tuple[tuple[date, ...], tuple[IndustryCloseSeries, ...]]:
    calendar = tuple(date(2025, 1, 1) + timedelta(days=index) for index in range(days))
    industries = []
    for position, (code, name, slope, wave) in enumerate(
        (
            ("801010.SI", "合成行业甲", 0.0015, 0.0007),
            ("801020.SI", "合成行业乙", 0.0004, -0.0005),
            ("801030.SI", "合成行业丙", -0.0008, 0.0002),
            ("801040.SI", "合成行业丁", -0.0002, -0.0006),
        )
    ):
        closes = {
            day: 100 * (1 + slope) ** index * (1 + wave * ((index + position) % 7))
            for index, day in enumerate(calendar)
        }
        industries.append(
            IndustryCloseSeries(
                industry_code=code,
                industry_name=name,
                closes=closes,
                constituent_counts={day: 10 + position for day in calendar},
            )
        )
    return calendar, tuple(industries)


def _build() -> MarketRotationSnapshot:
    calendar, industries = _inputs()
    return build_rotation_snapshot(
        data_snapshot_id="snapshot:sha256:" + "1" * 64,
        as_of=datetime(2025, 5, 21, tzinfo=UTC),
        created_at=datetime(2025, 5, 21, tzinfo=UTC),
        calendar=calendar,
        industries=industries,
        formula=production_formula(),
    )


def test_rotation_is_deterministic_bounded_and_not_a_trade_instruction() -> None:
    first = _build()
    second = _build()
    assert first.rotation_snapshot_id == second.rotation_snapshot_id
    assert len(first.dates) == 60
    assert len(first.points) == 4 * 60
    assert {point.quadrant for point in first.points} <= {
        "leading",
        "weakening",
        "lagging",
        "improving",
    }
    assert all(85 <= point.relative_trend <= 115 for point in first.points)
    assert all(85 <= point.relative_momentum <= 115 for point in first.points)
    assert all(point.raw_z_trend is not None for point in first.points)
    assert all(
        point.display_transform_version == DISPLAY_TRANSFORM_VERSION for point in first.points
    )
    assert "order" not in first.model_dump_json().lower()


def test_rotation_fails_closed_for_missing_price_and_low_constituent_count() -> None:
    calendar, industries = _inputs()
    missing = dict(industries[0].closes)
    missing.pop(calendar[-2])
    altered = (
        IndustryCloseSeries(
            industry_code=industries[0].industry_code,
            industry_name=industries[0].industry_name,
            closes=missing,
            constituent_counts=industries[0].constituent_counts,
        ),
        *industries[1:],
    )
    with pytest.raises(ValueError, match="面板缺失"):
        build_rotation_snapshot(
            data_snapshot_id="snapshot:sha256:" + "1" * 64,
            as_of=datetime(2025, 5, 21, tzinfo=UTC),
            created_at=datetime(2025, 5, 21, tzinfo=UTC),
            calendar=calendar,
            industries=altered,
            formula=production_formula(),
        )

    counts = dict(industries[0].constituent_counts)
    counts[calendar[-1]] = 2
    altered_count = (
        IndustryCloseSeries(
            industry_code=industries[0].industry_code,
            industry_name=industries[0].industry_name,
            closes=industries[0].closes,
            constituent_counts=counts,
        ),
        *industries[1:],
    )
    with pytest.raises(ValueError, match="成分不足"):
        build_rotation_snapshot(
            data_snapshot_id="snapshot:sha256:" + "1" * 64,
            as_of=datetime(2025, 5, 21, tzinfo=UTC),
            created_at=datetime(2025, 5, 21, tzinfo=UTC),
            calendar=calendar,
            industries=altered_count,
            formula=production_formula(),
        )


def test_rotation_store_is_immutable_and_detects_corruption(tmp_path: Path) -> None:
    snapshot = _build()
    store = FilesystemRotationStore(tmp_path)
    path = store.publish(snapshot)
    assert store.get_current() == snapshot
    assert store.publish(snapshot) == path

    path.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError):
        store.get_current()


def test_rotation_store_keeps_legacy_snapshot_identity_without_null_rewrite(
    tmp_path: Path,
) -> None:
    payload = _build().model_dump(mode="json")
    for point in payload["points"]:
        point.pop("raw_z_trend")
        point.pop("raw_z_momentum")
        point.pop("display_transform_version")
    parsed = MarketRotationSnapshot.model_validate_json(json.dumps(payload))
    identity = {
        "data_snapshot_id": parsed.data_snapshot_id,
        "as_of": parsed.as_of,
        "formula": parsed.formula.model_dump(mode="json"),
        "dates": parsed.dates,
        "points": [point.model_dump(mode="json", exclude_unset=True) for point in parsed.points],
        "events": [event.model_dump(mode="json") for event in parsed.events],
        "known_gaps": sorted(parsed.known_gaps),
    }
    digest = content_hash(identity)
    legacy = parsed.model_copy(
        update={
            "content_hash": digest,
            "rotation_snapshot_id": "rotation:" + digest,
        }
    )
    store = FilesystemRotationStore(tmp_path)
    path = store.publish(legacy)
    assert '"raw_z_trend"' not in path.read_text(encoding="utf-8")
    restored = store.get_current()
    assert restored.points[0].raw_z_trend is None
    assert restored.rotation_snapshot_id == legacy.rotation_snapshot_id
