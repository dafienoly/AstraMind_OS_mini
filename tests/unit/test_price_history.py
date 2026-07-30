import json
from datetime import UTC, date, datetime
from hashlib import sha256
from pathlib import Path

import duckdb
import pytest
from fastapi.testclient import TestClient

from astramind_mini.composition import create_app
from astramind_mini.config import Settings
from astramind_mini.contracts import DatasetRef, DataSnapshot
from astramind_mini.market_regime.adapters.price_history import SnapshotPriceHistory
from astramind_mini.market_regime.contracts.hierarchy import PriceCandle


def test_stock_listed_since_history_is_stably_paginated_and_cutoff_bounded(
    tmp_path: Path,
) -> None:
    snapshot_id = _fixture(tmp_path)
    reader = SnapshotPriceHistory(tmp_path)
    cursor = None
    observed: list[PriceCandle] = []
    identities = set()
    while True:
        page = reader.load(
            snapshot_id,
            "stock",
            "600001.SH",
            window="listed_since",
            evidence_cutoff=date(2026, 7, 28),
            cursor=cursor,
            page_size=200,
        )
        identities.add(
            (
                page.data_snapshot_id,
                page.dataset_version,
                page.evidence_cutoff,
                page.requested_start,
                page.requested_end,
            )
        )
        observed.extend(page.bars)
        if not page.has_more:
            break
        assert page.next_cursor is not None
        cursor = page.next_cursor

    assert len(identities) == 1
    assert min(item.trade_date for item in observed) == date(2020, 1, 2)
    assert max(item.trade_date for item in observed) <= date(2026, 7, 28)
    assert len({item.trade_date for item in observed}) == len(observed)
    assert page.coverage_start == date(2020, 1, 2)
    assert page.listing_date == date(2020, 1, 2)


def test_etf_coverage_truthfully_reports_history_after_listing(tmp_path: Path) -> None:
    snapshot_id = _fixture(tmp_path)

    page = SnapshotPriceHistory(tmp_path).load(
        snapshot_id,
        "etf",
        "510001.SH",
        window="listed_since",
        page_size=1000,
    )

    assert page.listing_date == date(2018, 1, 2)
    assert page.coverage_start == date(2021, 1, 4)
    assert "history_starts_after_listing:2018-01-02" in page.known_gaps
    assert page.coverage_basis == "listing_date_or_earliest_reliable_record"


def test_index_uses_earliest_reliable_record_without_claiming_year_2000(
    tmp_path: Path,
) -> None:
    snapshot_id = _fixture(tmp_path)

    page = SnapshotPriceHistory(tmp_path).load(
        snapshot_id,
        "index",
        "000300.SH",
        window="listed_since",
        page_size=1000,
    )

    assert page.coverage_start == date(2005, 1, 4)
    assert page.listing_date is None
    assert page.coverage_basis == "official_launch_or_earliest_reliable_record"


def test_explicit_market_window_keeps_the_frozen_evidence_availability_cutoff(
    tmp_path: Path,
) -> None:
    snapshot_id = _fixture(tmp_path)

    page = SnapshotPriceHistory(tmp_path).load(
        snapshot_id,
        "stock",
        "600001.SH",
        evidence_cutoff=date(2026, 7, 28),
        start=date(2021, 1, 4),
        end=date(2021, 1, 8),
        page_size=100,
    )

    assert [item.trade_date for item in page.bars] == [
        date(2021, 1, 4),
        date(2021, 1, 5),
        date(2021, 1, 6),
        date(2021, 1, 7),
        date(2021, 1, 8),
    ]
    assert page.evidence_cutoff == date(2026, 7, 28)
    assert page.requested_end == date(2021, 1, 8)


def test_cursor_outside_the_frozen_window_is_rejected(tmp_path: Path) -> None:
    snapshot_id = _fixture(tmp_path)

    with pytest.raises(ValueError, match="游标不在冻结日期窗口"):
        SnapshotPriceHistory(tmp_path).load(
            snapshot_id,
            "stock",
            "600001.SH",
            window="five_years",
            cursor=date(2020, 1, 1),
        )


def test_history_api_exposes_cursor_and_keeps_exact_snapshot_identity(
    tmp_path: Path,
) -> None:
    snapshot_id = _fixture(tmp_path)
    client = TestClient(create_app(Settings(environment="test", data_dir=tmp_path)))

    response = client.get(
        "/api/market/history/stock/600001.SH",
        params={
            "window": "listed_since",
            "data_snapshot_id": snapshot_id,
            "evidence_cutoff": "2026-07-28",
            "page_size": 100,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["data_snapshot_id"] == snapshot_id
    assert payload["has_more"] is True
    assert payload["next_cursor"] is not None
    assert len(payload["bars"]) == 100


def _fixture(root: Path) -> str:
    stock = _write(
        root,
        "daily_market",
        """
        SELECT '600001.SH' instrument_id, CAST(day AS DATE) trade_date,
               10.0 "open", 11.0 high, 9.0 low, 10.5 "close",
               1000.0 volume_lots, 2000.0 amount_thousand_cny,
               TIMESTAMPTZ '2026-07-28 18:00:00+08' available_at
        FROM generate_series(DATE '2020-01-02', DATE '2026-07-29', INTERVAL 1 DAY) t(day)
        WHERE dayofweek(day) BETWEEN 1 AND 5
        """,
    )
    security = _write(
        root,
        "security_master",
        """
        SELECT '600001.SH' instrument_id, '测试股票' "name",
               DATE '2020-01-02' list_date,
               TIMESTAMPTZ '2020-01-02 18:00:00+08' available_at
        """,
    )
    etf = _write(
        root,
        "etf_daily",
        """
        SELECT '510001.SH' instrument_id, CAST(day AS DATE) trade_date,
               1.0 "open", 1.1 high, 0.9 low, 1.05 "close",
               1000.0 volume_lots, 2000000.0 amount_cny,
               TIMESTAMPTZ '2026-07-28 18:00:00+08' available_at
        FROM generate_series(DATE '2021-01-04', DATE '2026-07-28', INTERVAL 1 DAY) t(day)
        WHERE dayofweek(day) BETWEEN 1 AND 5
        """,
    )
    master = _write(
        root,
        "etf_master",
        """
        SELECT '510001.SH' instrument_id, '测试ETF' "name",
               DATE '2018-01-02' list_date,
               TIMESTAMPTZ '2026-07-28 18:00:00+08' available_at
        """,
    )
    index = _write(
        root,
        "broad_index_daily",
        """
        SELECT '000300.SH' instrument_id, '沪深300' instrument_name,
               CAST(day AS DATE) trade_date, 3000.0 "open", 3010.0 high,
               2990.0 low, 3005.0 "close", 1000.0 volume_lots,
               2000000.0 amount_cny
        FROM generate_series(DATE '2005-01-04', DATE '2026-07-28', INTERVAL 1 DAY) t(day)
        WHERE dayofweek(day) BETWEEN 1 AND 5
        """,
    )
    references = tuple(
        DatasetRef(
            dataset_name=name,
            dataset_version=version,
            schema_version="1.0.0",
            content_hash=version,
        )
        for name, version in (stock, security, etf, master, index)
    )
    snapshot = DataSnapshot(
        snapshot_id="snapshot:sha256:" + "f" * 64,
        as_of=datetime(2026, 7, 29, 10, tzinfo=UTC),
        datasets=references,
        created_at=datetime(2026, 7, 29, 10, tzinfo=UTC),
        code_identity="price-history-fixture",
    )
    directory = root / "snapshots" / ("f" * 64)
    directory.mkdir(parents=True)
    (directory / "manifest.json").write_text(snapshot.model_dump_json(), encoding="utf-8")
    _write_current_pointer(root, snapshot.snapshot_id)
    return snapshot.snapshot_id


def _write_current_pointer(root: Path, snapshot_id: str) -> None:
    current = root / "current"
    current.mkdir()
    (current / "data-snapshot.json").write_text(
        json.dumps({"snapshot_id": snapshot_id}),
        encoding="utf-8",
    )


def _write(root: Path, name: str, query: str) -> tuple[str, str]:
    digest = sha256(name.encode()).hexdigest()
    version = f"sha256:{digest}"
    directory = root / "datasets" / name / digest
    directory.mkdir(parents=True)
    artifact = directory / f"{name}.parquet"
    with duckdb.connect(":memory:") as connection:
        connection.execute(f"COPY ({query}) TO ? (FORMAT PARQUET)", [str(artifact)])
    (directory / "manifest.json").write_text(
        json.dumps(
            {
                "dataset_version": version,
                "content_hash": version,
                "artifact_paths": [artifact.name],
                "known_gaps": [],
            }
        ),
        encoding="utf-8",
    )
    return name, version
