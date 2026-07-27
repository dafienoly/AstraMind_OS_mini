from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from astramind_mini.data.adapters import (
    FilesystemDatasetStore,
    FilesystemRawRecordStore,
    FilesystemSnapshotStore,
    ImmutableConflictError,
)
from astramind_mini.data.application import (
    DataSnapshotBuilder,
    build_dataset_manifest,
    content_hash,
)
from astramind_mini.data.contracts import DatasetManifest, RawRecordEnvelope


def manifest(
    *,
    payload: bytes = b"one",
    retrieved_at: datetime = datetime(2026, 1, 15, tzinfo=UTC),
    critical_gaps: tuple[str, ...] = (),
    known_gaps: tuple[str, ...] = (),
) -> tuple[DatasetManifest, dict[str, bytes]]:
    artifacts = {"data.parquet": payload}
    return (
        build_dataset_manifest(
            dataset_name="security_master",
            schema_version="1.0.0",
            provider="synthetic",
            source_endpoint="fixture",
            request_identity=content_hash({"request": 1}),
            retrieved_at=retrieved_at,
            market_timezone="Asia/Shanghai",
            date_range=(date(2026, 1, 1), date(2026, 1, 15)),
            universe=("000001.SZ",),
            primary_key=("instrument_id",),
            availability_rule="available_at <= as_of",
            units=(),
            row_count=1,
            artifacts=artifacts,
            known_gaps=known_gaps,
            critical_gaps=critical_gaps,
        ),
        artifacts,
    )


def test_snapshot_identity_is_stable_and_critical_gaps_fail_closed(tmp_path: Path) -> None:
    first, artifacts = manifest()
    builder = DataSnapshotBuilder()
    snapshot_a = builder.build(
        manifests=[first],
        as_of=datetime(2026, 1, 15, 15, tzinfo=UTC),
        created_at=datetime(2026, 1, 15, 16, tzinfo=UTC),
        code_identity="test-code",
    )
    snapshot_b = builder.build(
        manifests=[first],
        as_of=datetime(2026, 1, 15, 15, tzinfo=UTC),
        created_at=datetime(2026, 1, 15, 17, tzinfo=UTC),
        code_identity="test-code",
    )
    assert snapshot_a.snapshot_id == snapshot_b.snapshot_id

    dataset_store = FilesystemDatasetStore(tmp_path)
    dataset_store.publish(first, artifacts)
    snapshot_store = FilesystemSnapshotStore(tmp_path)
    first_snapshot_path = snapshot_store.publish(snapshot_a)
    assert snapshot_store.publish(snapshot_b) == first_snapshot_path
    assert snapshot_store.get(snapshot_a.snapshot_id) == snapshot_a

    blocked, _ = manifest(critical_gaps=("missing_page",))
    with pytest.raises(ValueError, match="关键数据缺口"):
        builder.build(
            manifests=[blocked],
            as_of=datetime(2026, 1, 15, 15, tzinfo=UTC),
            created_at=datetime(2026, 1, 15, 16, tzinfo=UTC),
            code_identity="test-code",
        )


def test_append_only_conflict_and_atomic_current_pointer(tmp_path: Path) -> None:
    envelope = RawRecordEnvelope(
        provider="synthetic",
        interface_name="fixture",
        source_endpoint="fixture",
        request_identity=content_hash({"request": "same"}),
        received_at=datetime(2026, 1, 15, tzinfo=UTC),
        schema_version="1.0.0",
        content_hash=content_hash({"value": 1}),
    )
    raw_store = FilesystemRawRecordStore(tmp_path)
    path = raw_store.append(envelope, {"value": 1})
    assert raw_store.append(envelope, {"value": 1}) == path
    with pytest.raises(ImmutableConflictError):
        raw_store.append(envelope, {"value": 2})

    dataset_store = FilesystemDatasetStore(tmp_path)
    first, first_artifacts = manifest(payload=b"one")
    second, second_artifacts = manifest(
        payload=b"two",
        retrieved_at=datetime(2026, 1, 16, tzinfo=UTC),
    )
    first_path = dataset_store.publish(first, first_artifacts)
    second_path = dataset_store.publish(second, second_artifacts)
    pointer = (tmp_path / "current/security_master.json").read_text(encoding="utf-8")
    assert first_path.exists() and second_path.exists()
    assert second.dataset_version in pointer


def test_snapshot_can_resolve_a_superseded_gap() -> None:
    item, _ = manifest(known_gaps=("daily_state_pending", "source_gap"))
    snapshot = DataSnapshotBuilder().build(
        manifests=[item],
        as_of=datetime(2026, 1, 15, 15, tzinfo=UTC),
        created_at=datetime(2026, 1, 15, 16, tzinfo=UTC),
        code_identity="test-code",
        resolved_gaps=("daily_state_pending",),
    )

    assert snapshot.known_gaps == ("source_gap",)
