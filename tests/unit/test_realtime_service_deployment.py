from pathlib import Path

from astramind_mini.local_ops.realtime_service_deployment import (
    TASK_NAME,
    RealtimeMarketTaskSpec,
    task_access_denied,
    task_is_present,
    task_xml,
)


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
