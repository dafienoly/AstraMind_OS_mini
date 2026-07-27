"""Internal strategy-independent research and backtest models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True, slots=True)
class ResearchBar:
    instrument_id: str
    trade_date: date
    open: float
    high: float
    low: float
    close: float
    research_close_index: float
    amount_cny: float
    turnover_rate: float | None
    listed_sessions: int
    risk_status: str
    buy_state: str
    sell_state: str
    has_daily_bar: bool = True
    upper_limit_locked: bool | None = None
    lower_limit_locked: bool | None = None


@dataclass(frozen=True, slots=True)
class UniverseRules:
    version: str = "tactical-universe-v1"
    minimum_listed_sessions: int = 60
    minimum_median_amount_20d_cny: float = 20_000_000
    maximum_order_participation: float = 0.05
    allow_event_coverage_channel: bool = True


@dataclass(frozen=True, slots=True)
class UniverseDecision:
    instrument_id: str
    as_of: date
    eligible: bool
    event_channel_eligible: bool
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CandidateSignal:
    instrument_id: str
    signal_date: date
    family: str
    horizon_sessions: int
    score: float
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class BacktestAssumptions:
    version: str = "a-share-daily-execution-v1"
    initial_cash_cny: float = 50_000
    maximum_positions: int = 2
    maximum_position_weight: float = 0.5
    lot_size: int = 100
    commission_rate: float = 0.0003
    minimum_commission_cny: float = 5
    stamp_duty_rate: float = 0.0005
    slippage_bps: float = 5
    maximum_order_participation: float = 0.05


@dataclass(frozen=True, slots=True)
class BacktestEvent:
    event_type: str
    instrument_id: str
    decision_date: date
    execution_date: date
    quantity: int
    price: float | None
    amount_cny: float
    reason: str


@dataclass(frozen=True, slots=True)
class ClosedTrade:
    instrument_id: str
    entry_date: date
    exit_date: date
    quantity: int
    entry_price: float
    exit_price: float
    net_profit_cny: float
    return_rate: float


@dataclass(frozen=True, slots=True)
class EquityPoint:
    trade_date: date
    equity_cny: float
    cash_cny: float
    positions: int


@dataclass(frozen=True, slots=True)
class BacktestMetrics:
    total_return: float
    annualized_return: float
    annualized_volatility: float
    sharpe: float
    max_drawdown: float
    win_rate: float
    payoff_ratio: float
    turnover: float
    closed_trades: int
    rejected_orders: int


@dataclass(frozen=True, slots=True)
class BacktestResult:
    strategy_family: str
    horizon_sessions: int
    assumptions: BacktestAssumptions
    events: tuple[BacktestEvent, ...]
    trades: tuple[ClosedTrade, ...]
    equity_curve: tuple[EquityPoint, ...]
    metrics: BacktestMetrics


__all__ = [
    "BacktestAssumptions",
    "BacktestEvent",
    "BacktestMetrics",
    "BacktestResult",
    "CandidateSignal",
    "ClosedTrade",
    "EquityPoint",
    "ResearchBar",
    "UniverseDecision",
    "UniverseRules",
]
