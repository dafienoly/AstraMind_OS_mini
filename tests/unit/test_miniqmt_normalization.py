from __future__ import annotations

from datetime import UTC, date, datetime, time
from zoneinfo import ZoneInfo

import pytest

from astramind_mini.data.application.identity import content_hash
from astramind_mini.data.application.miniqmt_normalization import (
    normalize_financial_facts,
    normalize_index_weights,
)
from astramind_mini.data.contracts import ProviderBatch

SHANGHAI = ZoneInfo("Asia/Shanghai")
RETRIEVED = datetime(2026, 7, 29, 6, tzinfo=UTC)


def batch(rows: tuple[dict[str, object], ...]) -> ProviderBatch:
    return ProviderBatch(
        provider_id="miniqmt",
        provider_version="xtquant_250516",
        native_interface="get_financial_data",
        source_endpoint="windows-xtdata-local-ndjson",
        request_identity=content_hash(rows),
        retrieved_at=RETRIEVED,
        rows=rows,
        raw_payload=rows,
        completeness=1,
    )


def next_close(announced: date) -> datetime:
    return datetime.combine(announced.replace(day=announced.day + 1), time(15), SHANGHAI)


def test_financial_facts_use_announcement_availability_and_keep_revision() -> None:
    rows = (
        {
            "instrument_id": "600519.SH",
            "statement_type": "Balance",
            "endDate": "20241231",
            "declareDate": "20250329",
            "totalAssets": 100.0,
        },
    )

    result = normalize_financial_facts(
        batch(rows),
        availability_resolver=next_close,
        field_units={"totalAssets": ("CNY", "CNY")},
    )

    assert len(result) == 1
    assert result[0].report_period == date(2024, 12, 31)
    assert result[0].available_at == datetime(2025, 3, 30, 15, tzinfo=SHANGHAI)
    assert result[0].unit == "CNY"
    assert result[0].revision_identity == content_hash(rows[0])


def test_financial_row_without_announcement_is_rejected() -> None:
    rows = (
        {
            "instrument_id": "600519.SH",
            "statement_type": "Balance",
            "endDate": "20241231",
            "totalAssets": 100.0,
        },
    )

    with pytest.raises(ValueError, match="公告日期"):
        normalize_financial_facts(
            batch(rows),
            availability_resolver=next_close,
            field_units={"totalAssets": ("CNY", "CNY")},
        )


def test_index_weight_snapshot_retains_current_only_semantics() -> None:
    source = batch(
        (
            {
                "index_id": "000300.SH",
                "instrument_id": "600519.SH",
                "weight": 4.2,
            },
        )
    )

    result = normalize_index_weights(source)

    assert result[0].membership_semantics == "current_snapshot"
    assert result[0].observed_on == RETRIEVED.date()
