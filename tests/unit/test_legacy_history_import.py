import json
from datetime import UTC, datetime
from pathlib import Path

import duckdb

from astramind_mini.data.adapters import LegacyAnnualCompactor, discover_legacy_release
from astramind_mini.data.application import file_hash
from astramind_mini.data.application.state_files import year_is_intact


def legacy_file(path: Path, *, factor: bool = False) -> None:
    path.parent.mkdir(parents=True)
    if factor:
        query = """
            SELECT '000001.SZ' ts_code, DATE '2000-01-04' trade_date,
                   12.5 adj_factor, 'task' _task_id,
                   repeat('a', 64) _raw_sha256, 'legacy-v1' _dataset_version
        """
    else:
        query = """
            SELECT '000001.SZ' ts_code, DATE '2000-01-04' trade_date,
                   10.0 open, 10.5 high, 9.8 low, 10.2 "close",
                   10.0 pre_close, 0.2 change, 2.0 pct_chg,
                   100.0 vol, 1020.0 amount, 'task' _task_id,
                   repeat('a', 64) _raw_sha256, 'legacy-v1' _dataset_version
        """
    with duckdb.connect(":memory:") as connection:
        output = str(path).replace("'", "''")
        connection.execute(f"COPY ({query}) TO '{output}' (FORMAT PARQUET)")


def test_formal_legacy_release_compacts_and_resumes_by_year(tmp_path: Path) -> None:
    release_root = tmp_path / "silver/legacy-v1/releases/release"
    daily = release_root / "daily/trade_date=2000-01-04/data.parquet"
    factor = release_root / "adj_factor/trade_date=2000-01-04/data.parquet"
    legacy_file(daily)
    legacy_file(factor, factor=True)
    (release_root / "market_panel_manifest.json").write_text(
        json.dumps(
            {
                "publication_status": "passed_for_formal_research",
                "release_content_sha256": "b" * 64,
                "dataset_version": "legacy-v1",
                "created_at": "2026-01-01T00:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )
    release = discover_legacy_release(tmp_path, "legacy-v1")
    output_daily = tmp_path / "stage/daily.parquet"
    output_factor = tmp_path / "stage/factor.parquet"
    compactor = LegacyAnnualCompactor()

    assert compactor.compact(
        table="daily",
        source_files=release.files_for_year("daily", 2000),
        supplement_files=(),
        output=output_daily,
        imported_at=datetime(2026, 1, 2, tzinfo=UTC),
    ) == (1, 1)
    compactor.compact(
        table="adj_factor",
        source_files=release.files_for_year("adj_factor", 2000),
        supplement_files=(),
        output=output_factor,
        imported_at=datetime(2026, 1, 2, tzinfo=UTC),
    )
    assert compactor.validate_pair(output_daily, output_factor) == (0, 0)
    with duckdb.connect(":memory:") as connection:
        available_at = connection.execute(
            "SELECT available_at FROM read_parquet(?)",
            [str(output_daily)],
        ).fetchone()
    assert available_at is not None
    assert available_at[0].isoformat() == "2000-01-04T18:00:00+08:00"
    assert year_is_intact(
        {
            "daily_path": str(output_daily),
            "daily_hash": file_hash(output_daily),
            "factor_path": str(output_factor),
            "factor_hash": file_hash(output_factor),
        }
    )
