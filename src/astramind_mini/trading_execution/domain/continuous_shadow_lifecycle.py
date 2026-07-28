"""Cross-day local Shadow projection with T+1 recovery."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime

from ..contracts.continuous_shadow import ContinuousShadowState, ShadowStatePosition
from .reconciliation import canonical_hash
from .shadow import (
    ShadowFill,
    ShadowPortfolioState,
    ShadowPosition,
    project_shadow_portfolio,
)


def apply_shadow_fills(
    state: ContinuousShadowState,
    fills: tuple[ShadowFill, ...],
    *,
    as_of: datetime,
    trading_date: date,
) -> ContinuousShadowState:
    if as_of.tzinfo is None:
        raise ValueError("持续 Shadow 检查点时间必须带时区")
    projected = project_shadow_portfolio(
        ShadowPortfolioState(
            cash_cny=state.cash_cny,
            positions=tuple(
                ShadowPosition(item.instrument_id, item.quantity, item.average_cost)
                for item in state.positions
            ),
            realized_profit_cny=state.realized_profit_cny,
        ),
        fills,
    )
    available = {item.instrument_id: item.available_quantity for item in state.positions}
    for fill in fills:
        if fill.filled_quantity <= 0:
            continue
        if fill.side == "sell":
            available[fill.instrument_id] = max(
                0,
                available.get(fill.instrument_id, 0) - fill.filled_quantity,
            )
        else:
            available.setdefault(fill.instrument_id, 0)
    positions = tuple(
        ShadowStatePosition(
            instrument_id=item.instrument_id,
            quantity=item.quantity,
            available_quantity=min(item.quantity, available.get(item.instrument_id, 0)),
            average_cost=item.average_cost,
        )
        for item in projected.positions
    )
    equity = projected.cash_cny + sum(
        item.quantity * item.average_cost for item in projected.positions
    )
    return _state(
        previous=state,
        trading_date=trading_date,
        as_of=as_of,
        cash_cny=projected.cash_cny,
        positions=positions,
        realized_profit_cny=projected.realized_profit_cny,
        equity_cny=equity,
    )


def roll_shadow_trading_day(
    state: ContinuousShadowState,
    *,
    trading_date: date,
    as_of: datetime,
) -> ContinuousShadowState:
    if trading_date <= state.trading_date:
        raise ValueError("持续 Shadow 交易日必须向前推进")
    positions = tuple(
        item.model_copy(update={"available_quantity": item.quantity}) for item in state.positions
    )
    return _state(
        previous=state,
        trading_date=trading_date,
        as_of=as_of,
        cash_cny=state.cash_cny,
        positions=positions,
        realized_profit_cny=state.realized_profit_cny,
        equity_cny=state.equity_cny,
    )


def mark_shadow_to_market(
    state: ContinuousShadowState,
    close_prices: Mapping[str, float],
    *,
    trading_date: date,
    as_of: datetime,
) -> ContinuousShadowState:
    if trading_date != state.trading_date:
        raise ValueError("Shadow 估值交易日必须与当前状态一致")
    missing = sorted(
        item.instrument_id
        for item in state.positions
        if item.instrument_id not in close_prices or close_prices[item.instrument_id] <= 0
    )
    if missing:
        raise ValueError("Shadow 持仓缺少有效收盘估值：" + ",".join(missing))
    equity = state.cash_cny + sum(
        item.quantity * close_prices[item.instrument_id] for item in state.positions
    )
    return _state(
        previous=state,
        trading_date=trading_date,
        as_of=as_of,
        cash_cny=state.cash_cny,
        positions=state.positions,
        realized_profit_cny=state.realized_profit_cny,
        equity_cny=equity,
    )


def _state(
    *,
    previous: ContinuousShadowState,
    trading_date: date,
    as_of: datetime,
    cash_cny: float,
    positions: tuple[ShadowStatePosition, ...],
    realized_profit_cny: float,
    equity_cny: float,
) -> ContinuousShadowState:
    sleeve_peak = max(previous.sleeve_peak_equity_cny, equity_cny)
    account_peak = max(previous.account_peak_equity_cny, equity_cny)
    identity = {
        "disposition_id": previous.disposition_id,
        "trading_date": trading_date,
        "as_of": as_of,
        "cash_cny": cash_cny,
        "positions": [item.model_dump(mode="json") for item in positions],
        "realized_profit_cny": realized_profit_cny,
        "equity_cny": equity_cny,
        "sleeve_peak_equity_cny": sleeve_peak,
        "account_equity_cny": equity_cny,
        "account_peak_equity_cny": account_peak,
    }
    digest = canonical_hash(identity)
    return ContinuousShadowState(
        state_id="continuous-shadow-state:" + digest.removeprefix("sha256:"),
        disposition_id=previous.disposition_id,
        trading_date=trading_date,
        as_of=as_of,
        cash_cny=cash_cny,
        positions=positions,
        realized_profit_cny=realized_profit_cny,
        equity_cny=equity_cny,
        sleeve_peak_equity_cny=sleeve_peak,
        account_equity_cny=equity_cny,
        account_peak_equity_cny=account_peak,
        content_hash=digest,
    )


__all__ = ["apply_shadow_fills", "mark_shadow_to_market", "roll_shadow_trading_day"]
