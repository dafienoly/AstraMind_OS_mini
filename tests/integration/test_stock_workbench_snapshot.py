from pathlib import Path

from astramind_mini.market_regime.adapters import SnapshotStockWorkbench
from scripts.e2e_rotation_fixture import prepare_data_snapshot


def test_real_snapshot_stock_workbench_serializes_candles_and_identity(
    tmp_path: Path,
) -> None:
    prepare_data_snapshot(tmp_path)

    projection = SnapshotStockWorkbench(tmp_path).current(
        "600001.SH",
        origin="watchlist",
        mode="current",
        return_target="market_stocks",
    )

    assert projection.instrument_identity.instrument_name == "合成股票01"
    assert projection.completed_market_evidence.daily
    assert projection.completed_market_evidence.evidence.provider == "synthetic-e2e"
    assert projection.content_identity.startswith("sha256:")
