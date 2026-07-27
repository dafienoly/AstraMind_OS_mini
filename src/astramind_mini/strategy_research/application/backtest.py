"""Strategy-independent A-share daily backtest engine."""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date
from statistics import mean, pstdev

from ..domain.backtest_models import (
    BacktestAssumptions,
    BacktestEvent,
    BacktestMetrics,
    BacktestResult,
    CandidateSignal,
    ClosedTrade,
    EquityPoint,
    ResearchBar,
    UniverseRules,
)
from .universe import evaluate_universe

SignalFunction = Callable[[Sequence[ResearchBar], int], CandidateSignal | None]


@dataclass(slots=True)
class _Position:
    instrument_id: str
    quantity: int
    entry_date: date
    decision_date: date
    entry_price: float
    entry_fee: float
    exit_session: int
    last_close: float


class DailyBacktestEngine:
    def __init__(
        self,
        assumptions: BacktestAssumptions | None = None,
        universe_rules: UniverseRules | None = None,
    ) -> None:
        self._assumptions = assumptions or BacktestAssumptions()
        self._universe_rules = universe_rules or UniverseRules()

    def run(
        self,
        *,
        bars: Sequence[ResearchBar],
        strategy_family: str,
        horizon_sessions: int,
        signal_function: SignalFunction,
    ) -> BacktestResult:
        if horizon_sessions not in {2, 5, 10}:
            raise ValueError("回测周期只能为 2/5/10 个交易日")
        by_date: dict[date, list[ResearchBar]] = defaultdict(list)
        for bar in sorted(bars, key=lambda item: (item.trade_date, item.instrument_id)):
            by_date[bar.trade_date].append(bar)
        if not by_date:
            raise ValueError("回测至少需要一个 Bar")
        histories: dict[str, list[ResearchBar]] = defaultdict(list)
        positions: dict[str, _Position] = {}
        pending: list[CandidateSignal] = []
        events: list[BacktestEvent] = []
        trades: list[ClosedTrade] = []
        curve: list[EquityPoint] = []
        cash = self._assumptions.initial_cash_cny
        turnover = 0.0
        for trade_date, day_bars in sorted(by_date.items()):
            current = {bar.instrument_id: bar for bar in day_bars}
            cash, sold = self._execute_exits(trade_date, current, positions, events, trades, cash)
            turnover += sold
            cash, bought = self._execute_entries(
                trade_date, current, pending, positions, events, cash
            )
            turnover += bought
            pending = []
            for bar in day_bars:
                histories[bar.instrument_id].append(bar)
                signal = signal_function(histories[bar.instrument_id], horizon_sessions)
                if signal is None:
                    continue
                decision = evaluate_universe(
                    histories[bar.instrument_id],
                    self._universe_rules,
                    event_attention=strategy_family == "event_attention",
                )
                if decision.eligible or decision.event_channel_eligible:
                    pending.append(signal)
            pending.sort(key=lambda item: (-item.score, item.instrument_id))
            for position in positions.values():
                if position.instrument_id in current:
                    position.last_close = current[position.instrument_id].close
            equity = cash + sum(
                position.quantity * position.last_close for position in positions.values()
            )
            curve.append(EquityPoint(trade_date, equity, cash, len(positions)))
        metrics = _metrics(
            curve,
            trades,
            events,
            turnover,
            self._assumptions.initial_cash_cny,
        )
        return BacktestResult(
            strategy_family=strategy_family,
            horizon_sessions=horizon_sessions,
            assumptions=self._assumptions,
            events=tuple(events),
            trades=tuple(trades),
            equity_curve=tuple(curve),
            metrics=metrics,
        )

    def _execute_entries(
        self,
        trade_date: date,
        bars: dict[str, ResearchBar],
        pending: Sequence[CandidateSignal],
        positions: dict[str, _Position],
        events: list[BacktestEvent],
        cash: float,
    ) -> tuple[float, float]:
        total = 0.0
        slots = self._assumptions.maximum_positions - len(positions)
        for signal in pending:
            if slots <= 0 or signal.instrument_id in positions:
                continue
            bar = bars.get(signal.instrument_id)
            if bar is None or bar.buy_state != "tradable":
                _reject(events, signal, trade_date, "buy_not_tradable")
                continue
            price = bar.open * (1 + self._assumptions.slippage_bps / 10_000)
            budget = min(
                cash,
                self._assumptions.initial_cash_cny * self._assumptions.maximum_position_weight,
                bar.amount_cny * self._assumptions.maximum_order_participation,
            )
            quantity = _board_lots(budget / price, self._assumptions.lot_size)
            fee = _commission(quantity * price, self._assumptions)
            while quantity > 0 and quantity * price + fee > cash:
                quantity -= self._assumptions.lot_size
                fee = _commission(quantity * price, self._assumptions)
            if quantity <= 0:
                _reject(events, signal, trade_date, "cash_or_liquidity_below_one_lot")
                continue
            amount = quantity * price
            cash -= amount + fee
            positions[signal.instrument_id] = _Position(
                signal.instrument_id,
                quantity,
                trade_date,
                signal.signal_date,
                price,
                fee,
                exit_session=max(1, signal.horizon_sessions - 1),
                last_close=bar.close,
            )
            events.append(
                BacktestEvent(
                    "filled_buy",
                    signal.instrument_id,
                    signal.signal_date,
                    trade_date,
                    quantity,
                    price,
                    amount,
                    "next_open",
                )
            )
            slots -= 1
            total += amount
        return cash, total

    def _execute_exits(
        self,
        trade_date: date,
        bars: dict[str, ResearchBar],
        positions: dict[str, _Position],
        events: list[BacktestEvent],
        trades: list[ClosedTrade],
        cash: float,
    ) -> tuple[float, float]:
        total = 0.0
        for instrument, position in tuple(positions.items()):
            position.exit_session -= 1
            if position.exit_session > 0:
                continue
            bar = bars.get(instrument)
            if bar is None or bar.sell_state != "tradable":
                events.append(
                    BacktestEvent(
                        "rejected_sell",
                        instrument,
                        position.decision_date,
                        trade_date,
                        position.quantity,
                        None,
                        0,
                        "sell_not_tradable",
                    )
                )
                continue
            price = bar.open * (1 - self._assumptions.slippage_bps / 10_000)
            amount = position.quantity * price
            fees = _commission(amount, self._assumptions)
            tax = amount * self._assumptions.stamp_duty_rate
            cash += amount - fees - tax
            cost = position.quantity * position.entry_price + position.entry_fee
            net_profit = amount - fees - tax - cost
            trades.append(
                ClosedTrade(
                    instrument,
                    position.entry_date,
                    trade_date,
                    position.quantity,
                    position.entry_price,
                    price,
                    net_profit,
                    net_profit / cost,
                )
            )
            events.append(
                BacktestEvent(
                    "filled_sell",
                    instrument,
                    position.decision_date,
                    trade_date,
                    position.quantity,
                    price,
                    amount,
                    "horizon_exit",
                )
            )
            del positions[instrument]
            total += amount
        return cash, total


def _board_lots(shares: float, lot_size: int) -> int:
    return max(0, int(shares // lot_size) * lot_size)


def _commission(amount: float, assumptions: BacktestAssumptions) -> float:
    if amount <= 0:
        return 0.0
    return max(assumptions.minimum_commission_cny, amount * assumptions.commission_rate)


def _reject(
    events: list[BacktestEvent],
    signal: CandidateSignal,
    execution_date: date,
    reason: str,
) -> None:
    events.append(
        BacktestEvent(
            "rejected_buy",
            signal.instrument_id,
            signal.signal_date,
            execution_date,
            0,
            None,
            0,
            reason,
        )
    )


def _metrics(
    curve: Sequence[EquityPoint],
    trades: Sequence[ClosedTrade],
    events: Sequence[BacktestEvent],
    turnover_amount: float,
    initial_cash: float,
) -> BacktestMetrics:
    equity = [point.equity_cny for point in curve]
    returns = [equity[index] / equity[index - 1] - 1 for index in range(1, len(equity))]
    total_return = equity[-1] / initial_cash - 1
    years = max(len(equity) / 252, 1 / 252)
    annualized = (max(equity[-1], 0.01) / initial_cash) ** (1 / years) - 1
    volatility = pstdev(returns) * math.sqrt(252) if len(returns) > 1 else 0.0
    sharpe = mean(returns) / pstdev(returns) * math.sqrt(252) if volatility > 0 else 0.0
    peak = equity[0]
    max_drawdown = 0.0
    for value in equity:
        peak = max(peak, value)
        max_drawdown = min(max_drawdown, value / peak - 1)
    winners = [trade.net_profit_cny for trade in trades if trade.net_profit_cny > 0]
    losers = [-trade.net_profit_cny for trade in trades if trade.net_profit_cny < 0]
    return BacktestMetrics(
        total_return=total_return,
        annualized_return=annualized,
        annualized_volatility=volatility,
        sharpe=sharpe,
        max_drawdown=max_drawdown,
        win_rate=len(winners) / len(trades) if trades else 0.0,
        payoff_ratio=mean(winners) / mean(losers) if winners and losers else 0.0,
        turnover=turnover_amount / initial_cash,
        closed_trades=len(trades),
        rejected_orders=sum(event.event_type.startswith("rejected") for event in events),
    )


__all__ = ["DailyBacktestEngine", "SignalFunction"]
