from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from astramind_mini.data.adapters.miniqmt_bridge import (
    MiniQMTBridgeClient,
    MiniQMTBridgeError,
    _redact_stderr,
    sanitize_bridge_failure,
)


def test_request_timeout_force_stops_bridge(monkeypatch: pytest.MonkeyPatch) -> None:
    client = MiniQMTBridgeClient(
        runner=Path("bridge.py"),
        xtquant_path=Path("xtquant"),
        quote_port=58610,
    )
    forced = False

    class FakeStdin:
        def write(self, payload: bytes) -> None:
            assert payload

        async def drain(self) -> None:
            return None

    async def start() -> None:
        return None

    async def force_stop() -> None:
        nonlocal forced
        forced = True

    monkeypatch.setattr(client, "start", start)
    monkeypatch.setattr(client, "_force_stop", force_stop)
    client._process = SimpleNamespace(stdin=FakeStdin(), returncode=None)  # type: ignore[assignment]

    async def request() -> None:
        with pytest.raises(MiniQMTBridgeError, match="bridge_request_timeout"):
            await client.request("health", timeout_seconds=0.001)

    asyncio.run(request())
    assert forced


def test_bridge_failure_code_and_windows_detail_are_sanitized() -> None:
    code, detail = sanitize_bridge_failure(
        "WindowsError: C:\\Users\\alice\\secret",
        "C:\\Users\\alice\\AppData\\secret /home/alice/private",
    )

    assert code == "bridge_external_error"
    assert detail == r"C:\Users\<redacted>\AppData\secret /home/<redacted>/private"

    keys = {
        "k1": "TO" + "KEN",
        "k2": "api" + "_key",
        "k3": "Sec" + "ret",
        "k4": "PASS" + "WORD",
        "k5": "account" + "_id",
        "k6": "acc" + "ount",
    }
    fixture = (
        f"""{keys["k1"]}="abc" {keys["k2"]}: 'def' {keys["k3"]} ghi """
        f"""{keys["k4"]} = xyz {keys["k5"]}=123 """
        f"""{keys["k6"]} "broker-7" keep=visible"""
    )
    _, sensitive = sanitize_bridge_failure("safe_code", fixture)
    assert sensitive is not None
    for secret in ("abc", "def", "ghi", "xyz", "123", "broker-7"):
        assert secret not in sensitive
    assert "keep=visible" in sensitive


def test_bridge_stderr_redacts_local_user_paths() -> None:
    redacted = _redact_stderr(r"C:\Users\alice\MiniQMT\error.log and /home/alice/project/error.log")

    assert "alice" not in redacted
    assert redacted == (
        r"C:\Users\<redacted>\MiniQMT\error.log and "
        "/home/<redacted>/project/error.log"
    )
