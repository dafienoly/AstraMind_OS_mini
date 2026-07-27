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


__all__ = [
    "OrderSide",
    "ShadowFill",
    "ShadowOrderLine",
    "ShadowPortfolioState",
    "ShadowPosition",
    "ShadowQuote",
]
