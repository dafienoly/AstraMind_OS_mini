from __future__ import annotations

from pathlib import Path

import pytest

from astramind_mini.data.application.source_route_policy import (
    SourceRoutePolicyStore,
    default_routes,
)
from astramind_mini.data.contracts import DatasetSourceRoute


def miniqmt_route() -> DatasetSourceRoute:
    return DatasetSourceRoute(
        dataset_name="daily_market",
        providers=("miniqmt", "tushare"),
        adapter_version="route-v1",
        quality_gate_version="benchmark-v1",
        timeout_seconds=30,
    )


def test_diagnostic_gate_cannot_activate_miniqmt_primary(tmp_path: Path) -> None:
    store = SourceRoutePolicyStore(tmp_path)

    with pytest.raises(ValueError, match="完整生产范围"):
        store.publish(
            (miniqmt_route(),),
            gate_evidence={"daily_market": "sha256:benchmark"},
        )


def test_production_gate_can_publish_immutable_route(tmp_path: Path) -> None:
    store = SourceRoutePolicyStore(tmp_path)

    policy_hash = store.publish(
        (miniqmt_route(),),
        gate_evidence={"daily_market": "sha256:benchmark"},
        production_scope=True,
    )

    assert store.load()[0].providers == ("miniqmt", "tushare")
    assert policy_hash.startswith("sha256:")
    assert (
        store.publish(
            (miniqmt_route(),),
            gate_evidence={"daily_market": "sha256:benchmark"},
            production_scope=True,
        )
        == policy_hash
    )


def test_default_routes_use_miniqmt_with_whole_batch_tushare_fallback() -> None:
    routes = {route.dataset_name: route for route in default_routes()}

    for dataset_name in ("daily_market", "broad_index_daily"):
        route = routes[dataset_name]
        assert route.providers == ("miniqmt", "tushare")
        assert route.quality_gate_version == "user-cost-override-20260729"
        assert route.primary_key == ("instrument_id", "trade_date")
        assert not route.allow_empty
