from datetime import datetime

import pytest
from pydantic import ValidationError

from astramind_mini.contracts import DatasetRef, DataSnapshot

HASH = "sha256:" + ("a" * 64)


def valid_snapshot() -> DataSnapshot:
    return DataSnapshot(
        snapshot_id="snapshot:test",
        as_of=datetime.fromisoformat("2026-01-15T15:30:00+08:00"),
        datasets=(
            DatasetRef(
                dataset_name="security_master",
                dataset_version="fixture-v1",
                schema_version="1.0.0",
                content_hash=HASH,
            ),
        ),
        known_gaps=(),
        created_at=datetime.fromisoformat("2026-01-15T16:00:00+08:00"),
        code_identity="fixture-code-v1",
    )


def test_contract_is_frozen_and_round_trips_json() -> None:
    snapshot = valid_snapshot()
    restored = DataSnapshot.model_validate_json(snapshot.model_dump_json())

    assert restored == snapshot
    with pytest.raises(ValidationError):
        snapshot.snapshot_id = "changed"


def test_contract_rejects_extra_fields_naive_time_and_bad_hash() -> None:
    payload = valid_snapshot().model_dump()
    payload["unexpected"] = "no"
    with pytest.raises(ValidationError):
        DataSnapshot.model_validate(payload)

    payload = valid_snapshot().model_dump()
    payload["as_of"] = datetime(2026, 1, 15, 15, 30)
    with pytest.raises(ValidationError):
        DataSnapshot.model_validate(payload)

    with pytest.raises(ValidationError):
        DatasetRef(
            dataset_name="test",
            dataset_version="v1",
            schema_version="1",
            content_hash="not-a-hash",
        )
