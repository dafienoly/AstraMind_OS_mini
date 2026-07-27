"""Internal tactical-sleeve target details."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TargetHolding:
    instrument_id: str
    weight: float
    reference_price: float


@dataclass(frozen=True, slots=True)
class TacticalTargetDetails:
    portfolio_target_id: str
    capital_cny: float
    holdings: tuple[TargetHolding, ...]
    cash_weight: float


__all__ = ["TacticalTargetDetails", "TargetHolding"]
