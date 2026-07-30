from datetime import date, datetime

import pytest
from pydantic import ValidationError

from astramind_mini.contracts import DatasetRef, DataSnapshot
from astramind_mini.strategy_research.core import (
    CORE_DATA_SEMANTICS,
    CORE_FEATURE_PACKAGES,
    CoreDatasetSlice,
    CoreFeatureValue,
    CoreInputLayer,
    CoreInputSnapshot,
    CoreMarketObservation,
    FeatureAvailabilityState,
    FinancialObservation,
    IndustryMembershipObservation,
    freeze_core_input_snapshot,
    point_in_time_industry_level,
    select_point_in_time_financial,
    select_point_in_time_industry,
    visible_core_market_observations,
)

TZ = datetime.fromisoformat("2026-01-01T00:00:00+08:00").tzinfo
CUTOFF = datetime(2026, 1, 30, 18, 0, tzinfo=TZ)
HASH_A = "sha256:" + ("a" * 64)
HASH_B = "sha256:" + ("b" * 64)
HASH_C = "sha256:" + ("c" * 64)


def test_core_semantics_and_three_package_specs_are_frozen() -> None:
    assert CORE_DATA_SEMANTICS.version == "core-data-semantics-v1"
    assert CORE_DATA_SEMANTICS.ohlc_source == "continuous_research_price_index"
    assert CORE_DATA_SEMANTICS.execution_source == "point_in_time_raw_price_volume"
    assert [
        (item.package_id, item.canonical_dimension)
        for item in CORE_FEATURE_PACKAGES
    ] == [
        ("astramind-f0-v1", 24),
        ("qlib-alpha158-79633dd", 158),
        ("formulaic-alpha101-v3", 101),
    ]
    assert {item.data_semantics_version for item in CORE_FEATURE_PACKAGES} == {
        "core-data-semantics-v1"
    }
    assert {item.universe_version for item in CORE_FEATURE_PACKAGES} == {"U0-v1"}


def test_feature_availability_never_encodes_unknown_as_zero() -> None:
    missing = CoreFeatureValue(
        feature_id="EP_TTM",
        state=FeatureAvailabilityState.MISSING,
        reason_code="financial_input_missing",
    )
    assert missing.value is None

    with pytest.raises(ValidationError):
        CoreFeatureValue(
            feature_id="EP_TTM",
            state=FeatureAvailabilityState.MISSING,
            value=0.0,
            reason_code="financial_input_missing",
        )
    with pytest.raises(ValidationError):
        CoreFeatureValue(
            feature_id="INDUSTRY_REL_MOM_60_5",
            state=FeatureAvailabilityState.NOT_APPLICABLE,
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


def _snapshot(
    *,
    dataset_version: str = "daily-v1",
    content_hash: str = HASH_A,
) -> DataSnapshot:
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
        common_calendar_hash=HASH_B,
        universe_content_hash=HASH_C,
        datasets=(dataset or _slice(),),
    )


def test_core_input_snapshot_is_idempotent_and_every_content_change_reidentifies() -> None:
    baseline = _freeze()
    assert _freeze() == baseline
    assert baseline.core_input_snapshot_id.endswith(
        baseline.content_hash.removeprefix("sha256:")
    )

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
        _freeze(
            dataset=_slice(
                max_available_at=datetime(2026, 2, 2, 18, 0, tzinfo=TZ)
            )
        )
    with pytest.raises(ValueError, match="input layer is forbidden"):
        _freeze(dataset=_slice(input_layer=CoreInputLayer.CURRENT_SESSION))
