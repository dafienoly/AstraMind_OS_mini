"""Pure identities and fail-closed classification for read-only Paper startup."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from ..contracts.account import AccountSnapshot
from ..contracts.paper_startup import (
    BrokerAccountModeLock,
    PaperAccountBaseline,
    ReadonlyCallbackHandshake,
)
from .reconciliation import canonical_hash


def build_mode_lock(
    *,
    configured_mode: str,
    broker_account_matched: bool,
    broker_account_type: int,
    broker_account_classification: int | None,
    broker_account_status: int,
    client_version: str,
    gateway_version: str,
    verified_at: datetime,
) -> BrokerAccountModeLock:
    if configured_mode != "simulation":
        raise ValueError("Paper 只读握手只允许 simulation 配置")
    if not broker_account_matched:
        raise ValueError("券商返回中不存在唯一匹配的模拟盘账户")
    if broker_account_status not in {0, 6}:
        raise ValueError("券商账户状态未就绪")
    known_gaps: tuple[Literal["account_classification_not_returned"], ...] = (
        ("account_classification_not_returned",) if broker_account_classification is None else ()
    )
    payload = {
        "configured_mode": configured_mode,
        "broker_account_matched": True,
        "broker_account_type": broker_account_type,
        "broker_account_classification": broker_account_classification,
        "broker_account_status": broker_account_status,
        "mode_evidence": "configured_simulation_selector_matched",
        "known_gaps": known_gaps,
        "client_version": client_version,
        "gateway_version": gateway_version,
        "effective_mode": "simulation",
        "verified_at": verified_at,
    }
    digest = canonical_hash(payload)
    return BrokerAccountModeLock(
        mode_lock_id="broker-account-mode-lock:" + digest.removeprefix("sha256:"),
        configured_mode="simulation",
        broker_account_matched=True,
        broker_account_type=broker_account_type,
        broker_account_classification=broker_account_classification,
        broker_account_status=broker_account_status,
        mode_evidence="configured_simulation_selector_matched",
        known_gaps=known_gaps,
        client_version=client_version,
        gateway_version=gateway_version,
        effective_mode="simulation",
        verified_at=verified_at,
        content_hash=digest,
    )


def build_callback_handshake(
    *,
    mode_lock: BrokerAccountModeLock,
    snapshot: AccountSnapshot,
    subscribed: bool,
    unsubscribed: bool,
    callback_types: tuple[str, ...],
    callback_count: int,
    foreign_account_callback_count: int,
    disconnected: bool,
    started_at: datetime,
    completed_at: datetime,
) -> ReadonlyCallbackHandshake:
    if snapshot.account_mode != "simulation":
        raise ValueError("只读回调握手只能绑定模拟盘快照")
    if not subscribed or not unsubscribed:
        raise ValueError("只读回调订阅生命周期不完整")
    if foreign_account_callback_count:
        raise ValueError("收到非目标账户回调")
    allowed = {"account_status", "asset", "position", "order", "trade", "disconnected"}
    unique_types = tuple(sorted(set(callback_types)))
    if not set(unique_types) <= allowed:
        raise ValueError("只读回调类型未知")
    payload = {
        "mode_lock_id": mode_lock.mode_lock_id,
        "account_snapshot_id": snapshot.account_snapshot_id,
        "status": "ready" if callback_count else "quiet",
        "subscribed": True,
        "unsubscribed": True,
        "callback_types": unique_types,
        "callback_count": callback_count,
        "foreign_account_callback_count": 0,
        "disconnected": disconnected,
        "started_at": started_at,
        "completed_at": completed_at,
    }
    digest = canonical_hash(payload)
    return ReadonlyCallbackHandshake(
        handshake_id="readonly-callback-handshake:" + digest.removeprefix("sha256:"),
        mode_lock_id=mode_lock.mode_lock_id,
        account_snapshot_id=snapshot.account_snapshot_id,
        status="ready" if callback_count else "quiet",
        subscribed=True,
        unsubscribed=True,
        callback_types=unique_types,  # type: ignore[arg-type]
        callback_count=callback_count,
        foreign_account_callback_count=0,
        disconnected=disconnected,
        started_at=started_at,
        completed_at=completed_at,
        content_hash=digest,
    )


def build_paper_account_baseline(
    snapshot: AccountSnapshot,
    mode_lock: BrokerAccountModeLock,
    handshake: ReadonlyCallbackHandshake,
    *,
    created_at: datetime,
) -> PaperAccountBaseline:
    if snapshot.account_mode != mode_lock.effective_mode:
        raise ValueError("账户快照与模式锁不一致")
    inherited = tuple(sorted(item.instrument_id for item in snapshot.positions if item.quantity))
    open_orders = tuple(sorted(item.order_fingerprint for item in snapshot.orders if item.is_open))
    blockers = ["paper_write_not_authorized", "standing_mandate_missing"]
    if open_orders:
        blockers.append("preexisting_open_orders")
    if handshake.disconnected:
        blockers.append("callback_disconnected")
    payload = {
        "mode_lock_id": mode_lock.mode_lock_id,
        "handshake_id": handshake.handshake_id,
        "account_snapshot_id": snapshot.account_snapshot_id,
        "authority": "complete_miniqmt_simulation_account",
        "inherited_instrument_ids": inherited,
        "inherited_position_count": len(inherited),
        "managed_position_count": 0,
        "open_order_fingerprints": open_orders,
        "startup_state": "blocked" if blockers else "readonly_ready",
        "blocker_codes": tuple(sorted(blockers)),
        "created_at": created_at,
    }
    digest = canonical_hash(payload)
    return PaperAccountBaseline(
        baseline_id="paper-account-baseline:" + digest.removeprefix("sha256:"),
        mode_lock_id=mode_lock.mode_lock_id,
        handshake_id=handshake.handshake_id,
        account_snapshot_id=snapshot.account_snapshot_id,
        authority="complete_miniqmt_simulation_account",
        inherited_instrument_ids=inherited,
        inherited_position_count=len(inherited),
        managed_position_count=0,
        open_order_fingerprints=open_orders,
        startup_state="blocked" if blockers else "readonly_ready",
        blocker_codes=tuple(sorted(blockers)),
        created_at=created_at,
        content_hash=digest,
    )


__all__ = [
    "build_callback_handshake",
    "build_mode_lock",
    "build_paper_account_baseline",
]
