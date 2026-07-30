from pathlib import Path

from astramind_mini.local_ops.realtime_service_deployment import (
    TASK_NAME,
    RealtimeMarketTaskSpec,
    scheduler_query_state,
    task_access_denied,
    task_is_present,
    task_xml,
)
from scripts.manage_realtime_market_service import _append_bounded_log


def test_realtime_task_is_persistent_restartable_and_broker_free() -> None:
    spec = RealtimeMarketTaskSpec(
        distro="Ubuntu",
        repository_root=Path("/home/ly/work/AstraMind_OS_mini"),
        windows_user_sid="S-1-5-21-1-2-3-1001",
    )

    payload = task_xml(spec).decode("utf-16")

    assert TASK_NAME == "AstraMind OS Mini - Realtime Market"
    assert payload.count("LogonTrigger") == 2
    assert payload.count("CalendarTrigger") == 2
    assert "2026-01-01T08:55:00" in payload
    assert "RestartOnFailure" in payload
    assert "PT1M" in payload
    assert "IgnoreNew" in payload
    assert "PT0S" in payload
    assert "realtime-market-service-run" in payload
    assert "/home/ly/work/AstraMind_OS_mini" in payload
    assert "/bin/bash" in payload
    assert "-lc" in payload
    assert all(
        forbidden not in payload.lower()
        for forbidden in (
            "account" + "_id",
            "paper-canary",
            "order_stock",
            "cancel_order",
        )
    )


def test_scheduler_result_does_not_trust_wsl_exit_code_alone() -> None:
    assert task_access_denied("错误: 拒绝访问。", "")
    assert task_access_denied("", "ERROR: Access is denied.")
    assert not task_is_present("错误: 拒绝访问。", "")
    assert task_is_present(
        f"任务名: \\{TASK_NAME}\n状态: Ready",
        "",
    )
    assert scheduler_query_state(0, f"任务名: \\{TASK_NAME}", "") == "installed"
    assert (
        scheduler_query_state(1, "", "ERROR: The system cannot find the file specified.")
        == "not_installed"
    )
    assert scheduler_query_state(1, "", "ERROR: Access is denied.") == "query_failed"
    assert scheduler_query_state(255, "", "WSL interop failure") == "query_failed"
    assert (
        scheduler_query_state(1, f"ERROR while querying {TASK_NAME}", "Access is denied")
        == "query_failed"
    )


def test_task_log_is_rotated_and_bounded_while_process_is_running(tmp_path: Path) -> None:
    path = tmp_path / "service.log"
    _append_bounded_log(path, b"12345678", max_bytes=10)
    _append_bounded_log(path, b"abcdefgh", max_bytes=10)

    assert path.read_bytes() == b"abcdefgh"
    assert path.with_name("service.log.1").read_bytes() == b"12345678"
