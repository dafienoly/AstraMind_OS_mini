from __future__ import annotations

import json
import os
from datetime import UTC, date, datetime
from pathlib import Path

import duckdb
import pytest

from astramind_mini.data.adapters import (
    DataControlLedger,
    FilesystemDatasetStore,
    FilesystemSnapshotStore,
    ImmutableConflictError,
    immutable_artifacts,
)
from astramind_mini.data.application.datasets import (
    DataSnapshotBuilder,
    build_dataset_manifest_from_hashes,
)
from astramind_mini.data.application.identity import canonical_json, content_hash, file_hash
from astramind_mini.data.application.immutable_recovery import (
    ImmutableArtifactRecoveryService,
)
from astramind_mini.data.contracts import DatasetManifest

NOW = datetime(2026, 7, 30, 8, tzinfo=UTC)
DAY_ONE = date(2026, 7, 28)
DAY_TWO = date(2026, 7, 29)


def test_file_publication_is_physically_independent_and_stable(tmp_path: Path) -> None:
    source = tmp_path / "working.parquet"
    _write_daily(source, ((DAY_ONE, 10.0),))
    manifest = _manifest(source, row_count=1, date_range=(DAY_ONE, DAY_ONE))
    store = FilesystemDatasetStore(tmp_path / "data")

    published_manifest = store.publish_files(
        manifest,
        {"daily.parquet": (source, file_hash(source))},
    )
    published = published_manifest.parent / "daily.parquet"
    published_hash = file_hash(published)
    assert _inode(source) != _inode(published)

    replacement = tmp_path / "replacement.parquet"
    _write_daily(replacement, ((DAY_ONE, 10.0), (DAY_TWO, 11.0)))
    source.write_bytes(replacement.read_bytes())

    assert file_hash(published) == published_hash
    assert _inode(source) != _inode(published)


def test_copy_failure_leaves_no_visible_or_staged_dataset_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "data"
    source = tmp_path / "working.parquet"
    _write_daily(source, ((DAY_ONE, 10.0),))
    manifest = _manifest(source, row_count=1, date_range=(DAY_ONE, DAY_ONE))
    digest = manifest.dataset_version.rsplit(":", 1)[-1]
    directory = root / "datasets/daily_market" / digest

    def fail_copy(*_args: object, **_kwargs: object) -> None:
        raise OSError("synthetic interrupted copy")

    monkeypatch.setattr(immutable_artifacts, "_copy_file", fail_copy)
    with pytest.raises(OSError, match="interrupted copy"):
        FilesystemDatasetStore(root).publish_files(
            manifest,
            {"daily.parquet": (source, file_hash(source))},
        )

    assert not directory.exists()
    assert not tuple(directory.parent.glob(f".{digest}.*"))


@pytest.mark.parametrize(
    "fault",
    [
        "hash",
        "row_count",
        "primary_key",
        "date_range",
        "actual_range_narrower",
    ],
)
def test_integrity_fault_fails_before_current_pointer_changes(
    tmp_path: Path,
    fault: str,
) -> None:
    root = tmp_path / "data"
    source = tmp_path / "candidate.parquet"
    rows: tuple[tuple[date, float], ...] = ((DAY_ONE, 10.0), (DAY_TWO, 11.0))
    if fault == "primary_key":
        rows = ((DAY_ONE, 10.0), (DAY_ONE, 11.0))
    elif fault == "actual_range_narrower":
        rows = ((DAY_TWO, 11.0),)
    _write_daily(source, rows)
    date_range = (DAY_ONE, DAY_ONE) if fault == "date_range" else (DAY_ONE, DAY_TWO)
    row_count = 1 if fault in {"row_count", "actual_range_narrower"} else 2
    manifest = _manifest(source, row_count=row_count, date_range=date_range)
    expected_hash = "sha256:" + "0" * 64 if fault == "hash" else file_hash(source)
    pointer = root / "current/daily_market.json"
    pointer.parent.mkdir(parents=True)
    pointer.write_text('{"dataset_version":"previous"}', encoding="utf-8")

    with pytest.raises(ImmutableConflictError):
        FilesystemDatasetStore(root).publish_files(
            manifest,
            {"daily.parquet": (source, expected_hash)},
        )

    assert json.loads(pointer.read_text(encoding="utf-8")) == {"dataset_version": "previous"}


def test_explicit_recovery_preserves_old_identity_and_switches_to_new_snapshot(
    tmp_path: Path,
) -> None:
    root = tmp_path / "data"
    source = tmp_path / "mutable-working.parquet"
    _write_daily(source, ((DAY_ONE, 10.0),))
    previous = _manifest(source, row_count=1, date_range=(DAY_ONE, DAY_ONE))
    old_directory = (
        root / "datasets" / previous.dataset_name / previous.dataset_version.rsplit(":", 1)[-1]
    )
    old_directory.mkdir(parents=True)
    old_artifact = old_directory / "daily.parquet"
    os.link(source, old_artifact)
    (old_directory / "manifest.json").write_bytes(canonical_json(previous.model_dump(mode="json")))
    base = DataSnapshotBuilder().build(
        manifests=(previous,),
        as_of=NOW,
        created_at=NOW,
        code_identity="suspect-fixture",
    )
    base_path = FilesystemSnapshotStore(root).publish(base)
    current = root / "current/data-snapshot.json"
    current.parent.mkdir(parents=True)
    current.write_bytes(
        canonical_json(
            {
                "snapshot_id": base.snapshot_id,
                "manifest_path": str(base_path.relative_to(root)),
            }
        )
    )
    replacement = tmp_path / "replacement.parquet"
    _write_daily(replacement, ((DAY_ONE, 10.0), (DAY_TWO, 11.0)))
    source.write_bytes(replacement.read_bytes())
    assert _inode(source) == _inode(old_artifact)

    ledger = DataControlLedger(tmp_path / "control.sqlite3")
    ledger.migrate()
    result = ImmutableArtifactRecoveryService(
        data_root=root,
        datasets=FilesystemDatasetStore(root),
        snapshots=FilesystemSnapshotStore(root),
        ledger=ledger,
    ).recover(
        base_snapshot_id=base.snapshot_id,
        dataset_sources={"daily_market": {"daily.parquet": old_artifact}},
        created_at=NOW,
        code_identity="wp-0057-test-recovery",
    )

    assert result.snapshot.snapshot_id != base.snapshot_id
    assert json.loads(current.read_text(encoding="utf-8"))["snapshot_id"] == (
        result.snapshot.snapshot_id
    )
    assert (
        DatasetManifest.model_validate_json(
            (old_directory / "manifest.json").read_text(encoding="utf-8")
        )
        == previous
    )
    recovered_reference = result.snapshot.datasets[0]
    recovered_directory = (
        root / "datasets" / "daily_market" / recovered_reference.dataset_version.rsplit(":", 1)[-1]
    )
    recovered_manifest = DatasetManifest.model_validate_json(
        (recovered_directory / "manifest.json").read_text(encoding="utf-8")
    )
    assert recovered_manifest.row_count == 2
    assert recovered_manifest.date_range == (DAY_ONE, DAY_TWO)
    assert _inode(recovered_directory / "daily.parquet") != _inode(old_artifact)
    report = json.loads(result.recovery_report_path.read_text(encoding="utf-8"))
    assert report["datasets"][0]["previous_dataset_version"] == previous.dataset_version
    assert report["datasets"][0]["replacement_dataset_version"] == (
        recovered_manifest.dataset_version
    )


def _manifest(
    source: Path,
    *,
    row_count: int,
    date_range: tuple[date, date],
) -> DatasetManifest:
    artifact_hash = file_hash(source)
    return build_dataset_manifest_from_hashes(
        dataset_name="daily_market",
        schema_version="fixture-v1",
        provider="fixture",
        source_endpoint="fixture",
        request_identity=content_hash(
            {
                "artifact_hash": artifact_hash,
                "row_count": row_count,
                "date_range": date_range,
            }
        ),
        retrieved_at=NOW,
        market_timezone="Asia/Shanghai",
        date_range=date_range,
        universe=("000001.SZ",),
        primary_key=("instrument_id", "trade_date"),
        availability_rule="trade_date 18:00 Asia/Shanghai",
        units=("close:CNY",),
        row_count=row_count,
        artifact_hashes={"daily.parquet": artifact_hash},
    )


def _write_daily(path: Path, rows: tuple[tuple[date, float], ...]) -> None:
    values = ", ".join(
        f"('000001.SZ', DATE '{trade_date.isoformat()}', {close})" for trade_date, close in rows
    )
    escaped = str(path).replace("'", "''")
    with duckdb.connect(":memory:") as connection:
        connection.execute(
            "COPY (SELECT * FROM (VALUES "
            + values
            + ") AS t(instrument_id, trade_date, close) ORDER BY trade_date) "
            + f"TO '{escaped}' (FORMAT PARQUET)"
        )


def _inode(path: Path) -> tuple[int, int]:
    stat = path.stat()
    return stat.st_dev, stat.st_ino
