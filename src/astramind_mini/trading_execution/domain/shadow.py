"""Broker-free Shadow execution domain models."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class OrderSide(StrEnum):
    BUY = "buy"
    SELL = "sell"


@dataclass(frozen=True, slots=True)
class ShadowOrderLine:
    instrument_id: str
    side: OrderSide
    quantity: int
    reference_price: float


@dataclass(frozen=True, slots=True)
class ShadowQuote:
    instrument_id: str
    observed_at: datetime
    price: float
    available_quantity: int
    buy_state: str = "tradable"
    sell_state: str = "tradable"


@dataclass(frozen=True, slots=True)
class ShadowFill:
    instrument_id: str
    side: OrderSide
    requested_quantity: int
    filled_quantity: int
    price: float | None
    status: str
    reason: str


@dataclass(frozen=True, slots=True)
class ShadowPosition:
    instrument_id: str
    quantity: int
    average_cost: float


@dataclass(frozen=True, slots=True)
class ShadowPortfolioState:
    cash_cny: float
    positions: tuple[ShadowPosition, ...] = ()
    realized_profit_cny: float = 0


def project_shadow_portfolio(
    state: ShadowPortfolioState,
    fills: tuple[ShadowFill, ...],
    *,
    commission_rate: float = 0.0003,
    minimum_commission_cny: float = 5,
    stamp_duty_rate: float = 0.0005,
) -> ShadowPortfolioState:
    positions = {item.instrument_id: item for item in state.positions}
    cash = state.cash_cny
    realized = state.realized_profit_cny
    for fill in fills:
        if fill.filled_quantity <= 0 or fill.price is None:
            continue
        amount = fill.filled_quantity * fill.price
        commission = max(minimum_commission_cny, amount * commission_rate)
        current = positions.get(fill.instrument_id)
        if fill.side is OrderSide.BUY:
            if amount + commission > cash:
                raise ValueError("Shadow 成交后现金为负")
            existing_quantity = current.quantity if current else 0
            existing_cost = current.average_cost * existing_quantity if current else 0
            quantity = existing_quantity + fill.filled_quantity
            positions[fill.instrument_id] = ShadowPosition(
                fill.instrument_id,
                quantity,
                (existing_cost + amount + commission) / quantity,
            )
            cash -= amount + commission
        else:
            if current is None or current.quantity < fill.filled_quantity:
                raise ValueError("Shadow 卖出超过本地持仓")
            tax = amount * stamp_duty_rate
            realized += (
                (fill.price - current.average_cost) * fill.filled_quantity - commission - tax
            )
            remaining = current.quantity - fill.filled_quantity
            cash += amount - commission - tax
            if remaining:
                positions[fill.instrument_id] = ShadowPosition(
                    fill.instrument_id, remaining, current.average_cost
                )
            else:
                del positions[fill.instrument_id]
    return ShadowPortfolioState(
        cash_cny=cash,
        positions=tuple(positions[key] for key in sorted(positions)),
        realized_profit_cny=realized,
    )


__all__ = [
    "OrderSide",
    "ShadowFill",
    "ShadowOrderLine",
    "ShadowPortfolioState",
    "ShadowPosition",
    "ShadowQuote",
    "project_shadow_portfolio",
]
