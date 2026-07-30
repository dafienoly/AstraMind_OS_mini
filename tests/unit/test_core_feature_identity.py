from copy import deepcopy
from datetime import date, datetime
from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

from astramind_mini.contracts import DatasetRef, DataSnapshot
from astramind_mini.strategy_research.core import (
    ASTRAMIND_F0,
    CoreDatasetSlice,
    CoreInputLayer,
    CoreInputSnapshot,
    CoreRawFeatureBatchDraft,
    CoreRawFeatureEnvelope,
    CoreRawFeatureManifest,
    CoreRawFeatureRowDraft,
    FeatureAvailabilityState,
    finalize_core_raw_feature_envelope,
    freeze_core_input_snapshot,
    prepare_core_raw_feature_batch,
)
from astramind_mini.strategy_research.core.feature_identity import (
    canonical_definition_registry_hash,
    canonical_package_spec_hash,
)

TZ = datetime.fromisoformat("2026-01-01T00:00:00+08:00").tzinfo
CUTOFF = datetime(2026, 1, 30, 18, 0, tzinfo=TZ)
HASH_A = "sha256:" + ("a" * 64)
HASH_B = "sha256:" + ("b" * 64)
HASH_C = "sha256:" + ("c" * 64)
Path = tuple[str | int, ...]
Mutation = tuple[tuple[Path, object], ...]


def _core_input() -> CoreInputSnapshot:
    data_snapshot = DataSnapshot(
        snapshot_id="snapshot:identity-test",
        as_of=datetime(2026, 1, 30, 17, 30, tzinfo=TZ),
        datasets=(
            DatasetRef(
                dataset_name="adjusted_market",
                dataset_version="daily-v1",
                schema_version="1.0.0",
                content_hash=HASH_A,
            ),
        ),
        known_gaps=(),
        created_at=datetime(2026, 1, 30, 17, 45, tzinfo=TZ),
        code_identity="fixture-code-v1",
    )
    dataset = CoreDatasetSlice(
        dataset_name="adjusted_market",
        dataset_version="daily-v1",
        schema_version="1.0.0",
        content_hash=HASH_A,
        row_count=20,
        min_market_date=date(2026, 1, 1),
        max_market_date=date(2026, 1, 30),
        max_available_at=datetime(2026, 1, 30, 17, 0, tzinfo=TZ),
        input_layer=CoreInputLayer.COMPLETED_DAILY,
        sealed=True,
    )
    return freeze_core_input_snapshot(
        data_snapshot=data_snapshot,
        decision_date=date(2026, 1, 30),
        cutoff_at=CUTOFF,
        common_calendar_id="sse-szse-common-v1",
        common_calendar_hash=HASH_B,
        universe_content_hash=HASH_C,
        datasets=(dataset,),
    )


def _raw_rows() -> tuple[tuple[str, ...], tuple[CoreRawFeatureRowDraft, ...]]:
    order = tuple(
        f"{ASTRAMIND_F0.package_id}:feature-{index:03d}"
        for index in range(ASTRAMIND_F0.canonical_dimension)
    )
    rows = tuple(
        CoreRawFeatureRowDraft(
            instrument_id="600000.SH",
            decision_time=CUTOFF,
            feature_definition_id=feature_id,
            feature_definition_version="1.0.0",
            value_raw=float(index + 1),
            availability_state=FeatureAvailabilityState.OBSERVED,
        )
        for index, feature_id in enumerate(order)
    )
    return order, rows


def _artifacts() -> tuple[
    tuple[str, ...],
    CoreRawFeatureBatchDraft,
    CoreRawFeatureEnvelope,
]:
    order, rows = _raw_rows()
    draft = prepare_core_raw_feature_batch(
        core_input=_core_input(),
        package_spec=ASTRAMIND_F0,
        feature_order=order,
        rows=rows,
    )
    return order, draft, finalize_core_raw_feature_envelope(draft)


def _replace_path(value: Any, path: Path, replacement: object) -> Any:
    key, *remaining = path
    child = (
        _replace_path(value[key], tuple(remaining), replacement)
        if remaining
        else replacement
    )
    if isinstance(value, tuple):
        if not isinstance(key, int):
            raise TypeError("tuple paths require an integer index")
        items = list(value)
        items[key] = child
        return tuple(items)
    value[key] = child
    return value


def _assert_tampering_rejected(
    model_type: type[BaseModel],
    artifact: BaseModel,
    cases: tuple[Mutation, ...],
) -> None:
    for mutations in cases:
        payload = deepcopy(artifact.model_dump())
        for path, replacement in mutations:
            _replace_path(payload, path, replacement)
        with pytest.raises(ValidationError):
            model_type.model_validate(payload)


def test_canonical_package_and_definition_registry_hashes_are_manifested() -> None:
    order, draft, envelope = _artifacts()
    expected_package_hash = canonical_package_spec_hash(ASTRAMIND_F0)
    expected_registry_hash = canonical_definition_registry_hash(order, draft.rows)

    assert draft.package_spec_hash == expected_package_hash
    assert draft.definition_registry_hash == expected_registry_hash
    assert envelope.manifest.core_input_content_hash == _core_input().content_hash
    assert envelope.manifest.package_spec_hash == expected_package_hash
    assert envelope.manifest.definition_registry_hash == expected_registry_hash


def test_dump_tampering_is_rejected_by_raw_draft_contract() -> None:
    order, draft, _ = _artifacts()
    _assert_tampering_rejected(
        CoreRawFeatureBatchDraft,
        draft,
        (
            ((("rows", 0, "value_raw"), 999.0),),
            (
                (("rows", 0, "value_raw"), None),
                (("rows", 0, "availability_state"), FeatureAvailabilityState.MISSING),
                (("rows", 0, "missing_reason_code"), "formula_input_missing"),
            ),
            ((("rows_content_hash",), HASH_A),),
            ((("row_content_hashes", 0), HASH_A),),
            ((("content_hash",), HASH_A),),
            ((("feature_snapshot_id",), "feature-snapshot:tampered"),),
            ((("core_input_snapshot_id",), "core-input:tampered"),),
            ((("core_input_content_hash",), HASH_A),),
            ((("package_spec", "canonical_dimension"), 25),),
            ((("package_spec_hash",), HASH_A),),
            ((("definition_registry_hash",), HASH_A),),
            ((("feature_order",), tuple(reversed(order))),),
        ),
    )


def test_dump_tampering_is_rejected_by_raw_manifest_contract() -> None:
    order, _, envelope = _artifacts()
    manifest = envelope.manifest
    _assert_tampering_rejected(
        CoreRawFeatureManifest,
        manifest,
        (
            ((("rows_content_hash",), HASH_A),),
            ((("row_content_hashes", 0), HASH_A),),
            ((("content_hash",), HASH_A),),
            ((("manifest_id",), "core-raw-feature-manifest:tampered"),),
            ((("core_input_snapshot_id",), "core-input:tampered"),),
            ((("core_input_content_hash",), HASH_A),),
            ((("package_spec", "canonical_dimension"), 25),),
            ((("package_spec_hash",), HASH_A),),
            ((("definition_registry_hash",), HASH_A),),
            ((("feature_order",), tuple(reversed(order))),),
            ((("row_order", 0, "feature_definition_version"), "2.0.0"),),
        ),
    )


def test_dump_tampering_is_rejected_by_raw_envelope_contract() -> None:
    order, _, envelope = _artifacts()
    _assert_tampering_rejected(
        CoreRawFeatureEnvelope,
        envelope,
        (
            ((("rows", 0, "value_raw"), 999.0),),
            (
                (("rows", 0, "value_raw"), None),
                (("rows", 0, "availability_state"), FeatureAvailabilityState.MISSING),
                (("rows", 0, "missing_reason_code"), "formula_input_missing"),
                (("rows", 0, "missing_indicator"), True),
            ),
            ((("feature_snapshot", "content_hash"), HASH_A),),
            (
                (
                    ("feature_snapshot", "feature_snapshot_id"),
                    "feature-snapshot:tampered",
                ),
            ),
            ((("core_input_snapshot_id",), "core-input:tampered"),),
            ((("package_spec", "canonical_dimension"), 25),),
            ((("feature_order",), tuple(reversed(order))),),
            ((("manifest", "content_hash"), HASH_A),),
            ((("manifest", "manifest_id"), "core-raw-feature-manifest:tampered"),),
            ((("manifest", "package_spec_hash"), HASH_A),),
            ((("manifest", "definition_registry_hash"), HASH_A),),
            ((("manifest", "row_order", 0, "feature_definition_version"), "2.0.0"),),
        ),
    )


def test_same_package_id_cannot_hide_package_or_registry_drift() -> None:
    order, draft, envelope = _artifacts()
    package_drift = deepcopy(draft.model_dump())
    package_drift["package_spec"]["canonical_dimension"] = 25
    assert package_drift["package_spec"]["package_id"] == ASTRAMIND_F0.package_id
    with pytest.raises(ValidationError):
        CoreRawFeatureBatchDraft.model_validate(package_drift)

    registry_drift = deepcopy(envelope.model_dump())
    registry_drift["manifest"]["row_order"][0]["feature_definition_version"] = "2.0.0"
    assert registry_drift["feature_order"] == order
    with pytest.raises(ValidationError):
        CoreRawFeatureEnvelope.model_validate(registry_drift)
