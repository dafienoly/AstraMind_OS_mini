from datetime import date, datetime

import pytest
from pydantic import ValidationError

from astramind_mini.contracts import DatasetRef, DataSnapshot
from astramind_mini.strategy_research.core import (
    ASTRAMIND_F0,
    CORE_DATA_SEMANTICS,
    CORE_FEATURE_PACKAGES,
    CoreDataSemantics,
    CoreDatasetSlice,
    CoreFeaturePackageSpec,
    CoreFeatureValue,
    CoreImputationSource,
    CoreInputLayer,
    CoreInputSnapshot,
    CoreMarketObservation,
    CoreRawFeatureEnvelope,
    CoreRawFeatureRowDraft,
    FeatureAvailabilityState,
    FinancialObservation,
    IndustryMembershipObservation,
    build_core_raw_feature_envelope,
    finalize_core_raw_feature_envelope,
    freeze_core_input_snapshot,
    point_in_time_industry_level,
    prepare_core_raw_feature_batch,
    select_point_in_time_financial,
    select_point_in_time_industry,
    visible_core_market_observations,
)
from astramind_mini.strategy_research.core.packages import CORE_FEATURE_ORDERS

TZ = datetime.fromisoformat("2026-01-01T00:00:00+08:00").tzinfo
CUTOFF = datetime(2026, 1, 30, 18, 0, tzinfo=TZ)
HASH_A = "sha256:" + ("a" * 64)
HASH_B = "sha256:" + ("b" * 64)
HASH_C = "sha256:" + ("c" * 64)


def test_core_semantics_and_three_package_specs_are_frozen() -> None:
    assert CORE_DATA_SEMANTICS.version == "core-data-semantics-v1"
    assert CORE_DATA_SEMANTICS.ohlc_source == "continuous_research_price_index"
    assert CORE_DATA_SEMANTICS.execution_source == "point_in_time_raw_price_volume"
    assert [(item.package_id, item.canonical_dimension) for item in CORE_FEATURE_PACKAGES] == [
        ("astramind-f0-v1", 24),
        ("qlib-alpha158-79633dd", 158),
        ("formulaic-alpha101-v3", 101),
    ]
    assert {item.data_semantics_version for item in CORE_FEATURE_PACKAGES} == {
        "core-data-semantics-v1"
    }
    assert {item.universe_version for item in CORE_FEATURE_PACKAGES} == {"U0-v1"}
    assert CORE_DATA_SEMANTICS.feature_states == (
        FeatureAvailabilityState.OBSERVED,
        FeatureAvailabilityState.MISSING,
        FeatureAvailabilityState.NOT_APPLICABLE,
    )
    for invalid_states in (
        (FeatureAvailabilityState.OBSERVED, FeatureAvailabilityState.MISSING),
        (
            FeatureAvailabilityState.MISSING,
            FeatureAvailabilityState.OBSERVED,
            FeatureAvailabilityState.NOT_APPLICABLE,
        ),
    ):
        with pytest.raises(ValidationError):
            CoreDataSemantics(feature_states=invalid_states)
        with pytest.raises(ValidationError):
            CORE_DATA_SEMANTICS.model_copy(update={"feature_states": invalid_states})
    with pytest.raises(ValidationError):
        CoreFeaturePackageSpec(
            package_id="astramind-f0-v1",
            canonical_dimension=25,
            authoritative_source="REQ-2026-0007-v2.3.0-section-6",
            data_semantics_version="core-data-semantics-v1",
            universe_version="U0-v1",
            required_definition_registry_hash=ASTRAMIND_F0.required_definition_registry_hash,
        )


def _feature_value(**changes: object) -> CoreFeatureValue:
    payload = {
        "feature_snapshot_id": "feature-snapshot:test",
        "instrument_id": "600000.SH",
        "decision_time": CUTOFF,
        "feature_definition_id": "EP_TTM",
        "feature_definition_version": "1.0.0",
        "value_raw": 0.12,
        "availability_state": FeatureAvailabilityState.OBSERVED,
        "missing_reason_code": None,
        "value_winsorized": None,
        "value_standardized": None,
        "imputation_source": CoreImputationSource.NONE,
        "missing_indicator": False,
        "not_applicable_indicator": False,
        "neutralized_diagnostic": None,
        "data_semantics_version": "core-data-semantics-v1",
        **changes,
    }
    return CoreFeatureValue.model_validate(payload)


def test_feature_availability_fields_are_strictly_consistent() -> None:
    missing = _feature_value(
        value_raw=None,
        availability_state=FeatureAvailabilityState.MISSING,
        missing_reason_code="financial_input_missing",
        missing_indicator=True,
    )
    assert missing.value_raw is None
    invalid_changes = (
        {
            "value_raw": 0.0,
            "availability_state": FeatureAvailabilityState.MISSING,
            "missing_reason_code": "financial_input_missing",
            "missing_indicator": True,
        },
        {
            "value_raw": None,
            "availability_state": FeatureAvailabilityState.NOT_APPLICABLE,
            "missing_reason_code": "industry_level_unavailable",
        },
        {"imputation_source": CoreImputationSource.SW_L1_MEDIAN},
        {"value_winsorized": 0.1},
        {
            "value_raw": None,
            "availability_state": FeatureAvailabilityState.MISSING,
            "missing_reason_code": "financial_input_missing",
            "missing_indicator": True,
            "value_winsorized": 0.0,
            "value_standardized": 0.0,
        },
    )
    for changes in invalid_changes:
        with pytest.raises(ValidationError):
            _feature_value(**changes)


@pytest.mark.parametrize("bad_value", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_raw_and_processed_values_fail_closed(bad_value: float) -> None:
    with pytest.raises(ValidationError):
        CoreRawFeatureRowDraft(
            instrument_id="600000.SH",
            decision_time=CUTOFF,
            feature_definition_id="EP_TTM",
            feature_definition_version="1.0.0",
            value_raw=bad_value,
            availability_state=FeatureAvailabilityState.OBSERVED,
        )
    with pytest.raises(ValidationError):
        _feature_value(
            value_winsorized=bad_value,
            value_standardized=0.0,
        )


def test_future_industry_membership_is_excluded() -> None:
    old = IndustryMembershipObservation(
        instrument_id="600000.SH",
        valid_from=date(2025, 1, 1),
        sw_l1="bank",
        sw_l2="state_bank",
        sw_l3="large_bank",
        available_at=datetime(2025, 1, 2, 18, 0, tzinfo=TZ),
        source_record_hash=HASH_A,
    )
    future = IndustryMembershipObservation(
        instrument_id="600000.SH",
        valid_from=date(2026, 1, 1),
        sw_l1="non_bank",
        sw_l2="broker",
        sw_l3="broker",
        available_at=datetime(2026, 2, 2, 18, 0, tzinfo=TZ),
        source_record_hash=HASH_B,
    )
    selected = select_point_in_time_industry(
        (future, old),
        instrument_id="600000.SH",
        decision_date=date(2026, 1, 30),
        cutoff_at=CUTOFF,
    )
    assert selected == old
    l1_only = old.model_copy(update={"sw_l2": None, "sw_l3": None})
    assert point_in_time_industry_level(l1_only, level="sw_l2") is None


def test_future_financial_announcement_and_revision_do_not_rewrite_history() -> None:
    original = FinancialObservation(
        instrument_id="600000.SH",
        metric="net_profit",
        report_period=date(2025, 12, 31),
        value=100.0,
        revision_id="original",
        announcement_date=date(2026, 1, 29),
        source_record_hash=HASH_A,
    )
    future_announcement = FinancialObservation(
        instrument_id="600000.SH",
        metric="revenue",
        report_period=date(2025, 12, 31),
        value=900.0,
        revision_id="future-announcement",
        announcement_date=date(2026, 1, 30),
        source_record_hash=HASH_B,
    )
    revision = FinancialObservation(
        instrument_id="600000.SH",
        metric="net_profit",
        report_period=date(2025, 12, 31),
        value=80.0,
        revision_id="revision",
        announced_at=datetime(2026, 2, 2, 10, 0, tzinfo=TZ),
        source_record_hash=HASH_C,
    )
    sessions = (date(2026, 1, 29), date(2026, 1, 30), date(2026, 2, 2))
    selected = select_point_in_time_financial(
        (revision, original),
        instrument_id="600000.SH",
        metric="net_profit",
        report_period=date(2025, 12, 31),
        cutoff_at=CUTOFF,
        common_sessions=sessions,
    )
    not_yet_available = select_point_in_time_financial(
        (future_announcement,),
        instrument_id="600000.SH",
        metric="revenue",
        report_period=date(2025, 12, 31),
        cutoff_at=CUTOFF,
        common_sessions=sessions,
    )
    assert selected is not None
    assert selected.observation == original
    assert selected.available_at == datetime(2026, 1, 30, 15, 0, tzinfo=TZ)
    assert not_yet_available is None


def test_future_and_mutable_market_inputs_are_excluded() -> None:
    visible = CoreMarketObservation(
        instrument_id="600000.SH",
        market_date=date(2026, 1, 30),
        available_at=datetime(2026, 1, 30, 17, 0, tzinfo=TZ),
        input_layer=CoreInputLayer.COMPLETED_DAILY,
        content_hash=HASH_A,
    )
    current = visible.model_copy(
        update={"input_layer": CoreInputLayer.CURRENT_SESSION, "content_hash": HASH_B}
    )
    future = visible.model_copy(
        update={
            "market_date": date(2026, 2, 2),
            "available_at": datetime(2026, 2, 2, 17, 0, tzinfo=TZ),
            "content_hash": HASH_C,
        }
    )
    assert visible_core_market_observations(
        (future, current, visible),
        decision_date=date(2026, 1, 30),
        cutoff_at=CUTOFF,
    ) == (visible,)


def _snapshot(*, dataset_version: str = "daily-v1", content_hash: str = HASH_A) -> DataSnapshot:
    return DataSnapshot(
        snapshot_id="snapshot:core-test",
        as_of=datetime(2026, 1, 30, 17, 30, tzinfo=TZ),
        datasets=(
            DatasetRef(
                dataset_name="adjusted_market",
                dataset_version=dataset_version,
                schema_version="1.0.0",
                content_hash=content_hash,
            ),
        ),
        known_gaps=(),
        created_at=datetime(2026, 1, 30, 17, 45, tzinfo=TZ),
        code_identity="fixture-code-v1",
    )


def _slice(
    *,
    dataset_version: str = "daily-v1",
    content_hash: str = HASH_A,
    row_count: int = 20,
    min_market_date: date = date(2026, 1, 1),
    max_market_date: date = date(2026, 1, 30),
    max_available_at: datetime = datetime(2026, 1, 30, 17, 0, tzinfo=TZ),
    input_layer: CoreInputLayer = CoreInputLayer.COMPLETED_DAILY,
) -> CoreDatasetSlice:
    return CoreDatasetSlice(
        dataset_name="adjusted_market",
        dataset_version=dataset_version,
        schema_version="1.0.0",
        content_hash=content_hash,
        row_count=row_count,
        min_market_date=min_market_date,
        max_market_date=max_market_date,
        max_available_at=max_available_at,
        input_layer=input_layer,
        sealed=True,
    )


def _freeze(
    *,
    snapshot: DataSnapshot | None = None,
    dataset: CoreDatasetSlice | None = None,
    cutoff_at: datetime = CUTOFF,
) -> CoreInputSnapshot:
    return freeze_core_input_snapshot(
        data_snapshot=snapshot or _snapshot(),
        decision_date=date(2026, 1, 30),
        cutoff_at=cutoff_at,
        common_calendar_id="sse-szse-common-v1",
        common_sessions=(date(2026, 1, 30),),
        universe_content_hash=HASH_C,
        datasets=(dataset or _slice(),),
    )


def test_core_input_snapshot_is_idempotent_and_every_content_change_reidentifies() -> None:
    baseline = _freeze()
    assert _freeze() == baseline
    assert baseline.core_input_snapshot_id.endswith(baseline.content_hash.removeprefix("sha256:"))
    version_changed = _freeze(
        snapshot=_snapshot(dataset_version="daily-v2"),
        dataset=_slice(dataset_version="daily-v2"),
    )
    cutoff_changed = _freeze(cutoff_at=datetime(2026, 1, 30, 18, 30, tzinfo=TZ))
    rows_changed = _freeze(dataset=_slice(row_count=21))
    range_changed = _freeze(dataset=_slice(min_market_date=date(2025, 12, 31)))
    content_changed = _freeze(
        snapshot=_snapshot(content_hash=HASH_B),
        dataset=_slice(content_hash=HASH_B),
    )
    identities = {
        item.content_hash
        for item in (
            baseline,
            version_changed,
            cutoff_changed,
            rows_changed,
            range_changed,
            content_changed,
        )
    }
    assert len(identities) == 6


def test_core_input_snapshot_rejects_future_or_mutable_data() -> None:
    with pytest.raises(ValueError, match="crosses the core cutoff"):
        _freeze(dataset=_slice(max_available_at=datetime(2026, 2, 2, 18, 0, tzinfo=TZ)))
    with pytest.raises(ValueError, match="input layer is forbidden"):
        _freeze(dataset=_slice(input_layer=CoreInputLayer.CURRENT_SESSION))
    original_ref = _snapshot().datasets[0]
    duplicate_ref = original_ref.model_copy(
        update={"dataset_version": "daily-v2", "content_hash": HASH_B}
    )
    duplicate_snapshot = _snapshot().model_copy(update={"datasets": (original_ref, duplicate_ref)})
    with pytest.raises(ValueError, match="duplicate dataset names"):
        _freeze(snapshot=duplicate_snapshot)


def _raw_package_rows(
    package: CoreFeaturePackageSpec,
) -> tuple[tuple[str, ...], tuple[CoreRawFeatureRowDraft, ...]]:
    feature_order = CORE_FEATURE_ORDERS[package.package_id]
    rows = []
    exceptional_states = {
        (1, 0): (FeatureAvailabilityState.MISSING, None, "formula_input_missing"),
        (1, 1): (
            FeatureAvailabilityState.NOT_APPLICABLE,
            None,
            "strict_industry_level_unavailable",
        ),
    }
    for instrument_index, instrument_id in enumerate(("000001.SZ", "600000.SH")):
        for feature_index, feature_id in enumerate(feature_order):
            state, value, reason = exceptional_states.get(
                (instrument_index, feature_index),
                (
                    FeatureAvailabilityState.OBSERVED,
                    float(instrument_index + feature_index + 1),
                    None,
                ),
            )
            rows.append(
                CoreRawFeatureRowDraft(
                    instrument_id=instrument_id,
                    decision_time=CUTOFF,
                    feature_definition_id=feature_id,
                    feature_definition_version="1.0.0",
                    value_raw=value,
                    availability_state=state,
                    missing_reason_code=reason,
                )
            )
    return feature_order, tuple(rows)


def _build_raw(
    package: CoreFeaturePackageSpec,
    feature_order: tuple[str, ...],
    rows: tuple[CoreRawFeatureRowDraft, ...],
) -> CoreRawFeatureEnvelope:
    return build_core_raw_feature_envelope(
        core_input=_freeze(),
        package_spec=package,
        computation_manifest_hash=HASH_B,
        calculation_sessions=_freeze().common_sessions,
        feature_order=feature_order,
        rows=rows,
    )


@pytest.mark.parametrize("package", CORE_FEATURE_PACKAGES)
def test_all_three_packages_share_idempotent_two_stage_raw_envelope(
    package: CoreFeaturePackageSpec,
) -> None:
    core_input = _freeze()
    feature_order, rows = _raw_package_rows(package)
    prepared = prepare_core_raw_feature_batch(
        core_input=core_input,
        package_spec=package,
        computation_manifest_hash=HASH_B,
        calculation_sessions=core_input.common_sessions,
        feature_order=feature_order,
        rows=rows,
    )
    repeated = prepare_core_raw_feature_batch(
        core_input=core_input,
        package_spec=package,
        computation_manifest_hash=HASH_B,
        calculation_sessions=core_input.common_sessions,
        feature_order=feature_order,
        rows=tuple(reversed(rows)),
    )
    envelope = finalize_core_raw_feature_envelope(prepared)
    assert prepared == repeated
    assert envelope == _build_raw(package, feature_order, rows)
    assert "feature_snapshot_id" not in CoreRawFeatureRowDraft.model_fields
    assert envelope.core_input_snapshot_id == core_input.core_input_snapshot_id
    assert envelope.feature_snapshot.data_snapshot_id == core_input.data_snapshot.snapshot_id
    assert (envelope.package_spec, envelope.feature_order) == (package, feature_order)
    assert (
        envelope.manifest.row_count,
        envelope.manifest.instrument_count,
        envelope.manifest.missing_count,
        envelope.manifest.not_applicable_count,
    ) == (2 * package.canonical_dimension, 2, 1, 1)
    assert envelope.manifest.rows_content_hash == prepared.rows_content_hash
    assert (
        tuple(item.feature_definition_id for item in envelope.manifest.feature_coverage)
        == feature_order
    )
    assert all(
        item.feature_snapshot_id == envelope.feature_snapshot.feature_snapshot_id
        for item in envelope.rows
    )
    assert all(
        item.value_winsorized is None and item.value_standardized is None for item in envelope.rows
    )
    assert all(item.imputation_source == CoreImputationSource.NONE for item in envelope.rows)
    assert all(item.neutralized_diagnostic is None for item in envelope.rows)


def test_raw_envelope_rejects_order_changes_and_reidentifies_content() -> None:
    feature_order, rows = _raw_package_rows(ASTRAMIND_F0)
    baseline = _build_raw(ASTRAMIND_F0, feature_order, rows)
    with pytest.raises(ValueError, match="canonical package"):
        _build_raw(ASTRAMIND_F0, tuple(reversed(feature_order)), rows)
    changed_rows = (
        rows[0].model_copy(update={"value_raw": (rows[0].value_raw or 0.0) + 1.0}),
        *rows[1:],
    )
    content_changed = _build_raw(ASTRAMIND_F0, feature_order, changed_rows)
    assert content_changed.feature_snapshot.content_hash != baseline.feature_snapshot.content_hash


def test_raw_envelope_fails_closed_on_width_duplicates_and_wrong_cutoff() -> None:
    feature_order, rows = _raw_package_rows(ASTRAMIND_F0)
    with pytest.raises(ValueError, match="complete canonical package width"):
        _build_raw(ASTRAMIND_F0, feature_order, rows[:-1])
    with pytest.raises(ValueError, match="duplicate an instrument-feature"):
        _build_raw(ASTRAMIND_F0, feature_order, (*rows, rows[0]))
    with pytest.raises(ValueError, match="feature_order cannot contain duplicate"):
        _build_raw(ASTRAMIND_F0, (*feature_order[:-1], feature_order[0]), rows)
    wrong_time = rows[0].model_copy(
        update={"decision_time": datetime(2026, 1, 30, 17, 0, tzinfo=TZ)}
    )
    with pytest.raises(ValueError, match="CoreInputSnapshot cutoff"):
        _build_raw(ASTRAMIND_F0, feature_order, (wrong_time, *rows[1:]))
