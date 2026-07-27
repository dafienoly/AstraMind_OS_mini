from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, cast

import httpx
import pytest
from pydantic import SecretStr

from astramind_mini.config import Settings
from astramind_mini.data.adapters.provider_config import (
    TushareProbeConfig,
    load_tushare_probe_config,
)
from astramind_mini.data.adapters.tushare_probe import TushareCapabilityProbe
from astramind_mini.data.contracts import CapabilityState
from scripts.windows import miniqmt_readonly_probe


def response_body(rows: list[list[object]]) -> dict[str, object]:
    return {
        "code": 0,
        "msg": None,
        "data": {"fields": ["ts_code", "trade_date"], "items": rows},
    }


def test_tushare_probe_handles_success_empty_and_permission_without_secret() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        payload = json.loads(request.content)
        assert payload["token"] == "secret-test-token"
        if payload["api_name"] == "adj_factor":
            return httpx.Response(200, json={"code": -1, "msg": "无权限", "data": None})
        rows: list[list[object]] = (
            [] if payload["api_name"] == "daily_basic" else [["000001.SZ", "20260115"]]
        )
        return httpx.Response(200, json=response_body(rows))

    config = TushareProbeConfig.model_validate(
        {
            "api_url": "https://provider.invalid/api",
            "token": SecretStr("secret-test-token"),
            "rate_limit_per_minute": 500,
            "timeout_seconds": 1,
            "max_retries": 0,
        }
    )

    async def execute() -> tuple[object, object]:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await TushareCapabilityProbe(config, client).probe()

    untyped_report, untyped_records = asyncio.run(execute())
    report = cast(Any, untyped_report)
    records = cast(tuple[object, ...], untyped_records)

    assert calls == 5
    assert len(records) == 4
    states = {item.interface_name: item.state for item in report.capabilities}
    assert states["trade_cal"] is CapabilityState.AVAILABLE
    assert states["adj_factor"] is CapabilityState.PERMISSION_DENIED
    assert states["daily_basic"] is CapabilityState.EMPTY
    assert "secret-test-token" not in report.model_dump_json()


def test_provider_config_precedence_and_secret_masking(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = tmp_path / "provider.env"
    provider.write_text(
        "TUSHARE_API_URL=https://old.invalid/api\nTUSHARE_TOKEN=old-test-token\n",
        encoding="utf-8",
    )
    local = tmp_path / ".env.local"
    local.write_text("ASTRAMIND_TUSHARE_TOKEN=local-test-token\n", encoding="utf-8")
    monkeypatch.setenv("ASTRAMIND_TUSHARE_API_URL", "https://runtime.invalid/api")
    monkeypatch.chdir(tmp_path)
    config = load_tushare_probe_config(Settings(), provider, local)

    assert config.api_url == "https://runtime.invalid/api"
    assert config.token.get_secret_value() == "local-test-token"
    assert "local-test-token" not in repr(config)


class FakeXtData:
    def __init__(self) -> None:
        self.unsubscribed: list[int] = []

    def get_full_tick(self, symbols: list[str]) -> dict[str, dict[str, float]]:
        return {symbols[0]: {"lastPrice": 10.0}}

    def get_market_data_ex(self, *args: object, **kwargs: object) -> dict[str, object]:
        raise ModuleNotFoundError("missing test dependency", name="numpy")

    def get_trading_dates(self, *args: object, **kwargs: object) -> list[int]:
        return [20260115]

    def get_instrument_detail(self, *args: object) -> dict[str, str]:
        return {"InstrumentID": "000001.SH"}

    def subscribe_quote(self, *args: object, **kwargs: Any) -> int:
        kwargs["callback"]({"000001.SH": {"lastPrice": 10.0}})
        return 7

    def unsubscribe_quote(self, sequence: int) -> None:
        self.unsubscribed.append(sequence)


def test_windows_runner_always_unsubscribes_and_has_no_trading_surface(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeXtData()
    package = type("Package", (), {"__version__": "test"})()

    def importer(name: str) -> object:
        return fake if name.endswith(".xtdata") else package

    monkeypatch.setattr(
        "scripts.windows.miniqmt_readonly_probe.importlib.import_module",
        importer,
    )
    result = miniqmt_readonly_probe.run(["000001.SH"], 0.01)

    assert fake.unsubscribed == [7]
    capabilities = cast(list[dict[str, object]], result["capabilities"])
    assert any(
        item["interface_name"] == "get_l2_quote" and item["state"] == "not_probed"
        for item in capabilities
    )
    assert any(
        item["interface_name"] == "get_market_data_ex"
        and item["error_code"] == "call_module_missing_numpy"
        for item in capabilities
    )
    source = Path(miniqmt_readonly_probe.__file__).read_text(encoding="utf-8")
    forbidden = ("XtQuantTrader", "query_stock_", "order_stock", "cancel_order_stock")
    assert not any(token in source for token in forbidden)
