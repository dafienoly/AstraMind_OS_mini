"""Order-plan construction and deterministic local Shadow fills."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta

from astramind_mini.contracts import ExecutionEvent, ExecutionMode, OrderPlan
from astramind_mini.portfolio_risk.public import PortfolioTarget, TacticalTargetDetails

from ..domain.shadow import (
    OrderSide,
    ShadowFill,
    ShadowOrderLine,
    ShadowQuote,
    project_shadow_portfolio,
)


def build_shadow_order_plan(
    target: PortfolioTarget,
    details: TacticalTargetDetails,
    *,
    current_shares: Mapping[str, int],
    created_at: datetime,
) -> tuple[OrderPlan, tuple[ShadowOrderLine, ...]]:
    if created_at.tzinfo is None:
        raise ValueError("订单计划时间必须带时区")
    desired = {
        item.instrument_id: int(
            (details.capital_cny * item.weight / item.reference_price) // 100 * 100
        )
        for item in details.holdings
    }
    lines: list[ShadowOrderLine] = []
    references = {item.instrument_id: item.reference_price for item in details.holdings}
    for instrument_id in sorted(set(current_shares) | set(desired)):
        delta = desired.get(instrument_id, 0) - current_shares.get(instrument_id, 0)
        if delta:
            lines.append(
                ShadowOrderLine(
                    instrument_id,
                    OrderSide.BUY if delta > 0 else OrderSide.SELL,
                    abs(delta),
                    references.get(instrument_id, 0),
                )
            )
    payload = {
        "target": target.portfolio_target_id,
        "lines": [
            (line.instrument_id, line.side, line.quantity, line.reference_price) for line in lines
        ],
    }
    digest = _hash(payload)
    plan = OrderPlan(
        order_plan_id=f"order-plan:{digest[7:]}",
        portfolio_target_id=target.portfolio_target_id,
        standing_mandate_id=None,
        execution_mode=ExecutionMode.SHADOW,
        created_at=created_at,
        content_hash=digest,
    )
    return plan, tuple(lines)


def simulate_shadow(
    plan: OrderPlan,
    lines: Sequence[ShadowOrderLine],
    quotes: Mapping[str, ShadowQuote],
    *,
    now: datetime,
    stale_after: timedelta = timedelta(seconds=10),
) -> tuple[tuple[ShadowFill, ...], tuple[ExecutionEvent, ...]]:
    fills: list[ShadowFill] = []
    events: list[ExecutionEvent] = []
    for sequence, line in enumerate(lines):
        quote = quotes.get(line.instrument_id)
        fill = _fill(line, quote, now, stale_after)
        fills.append(fill)
        payload = {
            "plan": plan.order_plan_id,
            "sequence": sequence,
            "instrument": fill.instrument_id,
            "status": fill.status,
            "filled": fill.filled_quantity,
            "price": fill.price,
            "reason": fill.reason,
        }
        digest = _hash(payload)
        events.append(
            ExecutionEvent(
                execution_event_id=f"execution-event:{digest[7:]}",
                order_plan_id=plan.order_plan_id,
                execution_mode=ExecutionMode.SHADOW,
                event_type=f"shadow_{fill.status}",
                sequence=sequence,
                occurred_at=now,
                content_hash=digest,
            )
        )
    return tuple(fills), tuple(events)


def _fill(
    line: ShadowOrderLine,
    quote: ShadowQuote | None,
    now: datetime,
    stale_after: timedelta,
) -> ShadowFill:
    if quote is None:
        return ShadowFill(
            line.instrument_id, line.side, line.quantity, 0, None, "rejected", "no_quote"
        )
    if quote.observed_at.tzinfo is None or now.tzinfo is None:
        raise ValueError("Shadow 行情与执行时点必须带时区")
    if now - quote.observed_at > stale_after:
        return ShadowFill(
            line.instrument_id, line.side, line.quantity, 0, None, "rejected", "stale_quote"
        )
    state = quote.buy_state if line.side is OrderSide.BUY else quote.sell_state
    if state != "tradable":
        return ShadowFill(line.instrument_id, line.side, line.quantity, 0, None, "rejected", state)
    quantity = min(line.quantity, max(0, quote.available_quantity // 100 * 100))
    status = "filled" if quantity == line.quantity else ("partial" if quantity else "rejected")
    reason = "shadow_quote" if status == "filled" else "bounded_by_available_quantity"
    return ShadowFill(
        line.instrument_id,
        line.side,
        line.quantity,
        quantity,
        quote.price if quantity else None,
        status,
        reason,
    )


def _hash(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(payload.encode()).hexdigest()


__all__ = ["build_shadow_order_plan", "project_shadow_portfolio", "simulate_shadow"]
