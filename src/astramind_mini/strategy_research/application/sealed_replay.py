"""Portfolio replay over full-universe candidates produced by an exact snapshot."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date

from ..domain.backtest_models import (
    BacktestAssumptions,
    BacktestEvent,
    BacktestResult,
    ClosedTrade,
    EquityPoint,
)
from ..domain.sealed_models import ReplayCandidate
from ..ports import SealedReplaySource
from .backtest import calculate_metrics


@dataclass(frozen=True, slots=True)
class _Holding:
    candidate: ReplayCandidate
    quantity: int
    entry_price: float
    entry_fee: float


class SealedReplayRunner:
    def __init__(
        self,
        source: SealedReplaySource,
        assumptions: BacktestAssumptions | None = None,
    ) -> None:
        self._source = source
        self._assumptions = assumptions or BacktestAssumptions()

    def run(
        self,
        *,
        family: str,
        horizon_sessions: int,
        start_date: date,
        end_date: date,
    ) -> BacktestResult:
        dates = self._source.trading_dates(start_date=start_date, end_date=end_date)
        if not dates:
            raise ValueError("封存窗口没有交易日")
        candidates = self._source.candidates(
            family=family,
            horizon_sessions=horizon_sessions,
            start_date=start_date,
            end_date=end_date,
        )
        by_entry: dict[date, list[ReplayCandidate]] = defaultdict(list)
        for candidate in candidates:
            by_entry[candidate.entry_date].append(candidate)
        for values in by_entry.values():
            values.sort(key=lambda item: (-item.signal.score, item.signal.instrument_id))

        cash = self._assumptions.initial_cash_cny
        holdings: dict[str, _Holding] = {}
        events: list[BacktestEvent] = []
        trades: list[ClosedTrade] = []
        turnover = 0.0
        cash_by_date: dict[date, float] = {}
        active_by_date: dict[date, dict[str, int]] = {}
        selected: set[str] = set()
        for trade_date in dates:
            cash, sold = self._exits(trade_date, holdings, events, trades, cash)
            turnover += sold
            cash, bought = self._entries(trade_date, by_entry[trade_date], holdings, events, cash)
            turnover += bought
            selected.update(holdings)
            cash_by_date[trade_date] = cash
            active_by_date[trade_date] = {
                instrument: holding.quantity for instrument, holding in holdings.items()
            }
        if holdings:
            raise ValueError("封存窗口结束时仍有未平仓头寸")
        curve = self._equity_curve(
            dates=dates,
            instruments=tuple(sorted(selected)),
            active_by_date=active_by_date,
            cash_by_date=cash_by_date,
            start_date=start_date,
            end_date=end_date,
        )
        metrics = calculate_metrics(
            curve,
            trades,
            events,
            turnover,
            self._assumptions.initial_cash_cny,
        )
        return BacktestResult(
            strategy_family=family,
            horizon_sessions=horizon_sessions,
            assumptions=self._assumptions,
            events=tuple(events),
            trades=tuple(trades),
            equity_curve=curve,
            metrics=metrics,
        )

    def _entries(
        self,
        trade_date: date,
        candidates: list[ReplayCandidate],
        holdings: dict[str, _Holding],
        events: list[BacktestEvent],
        cash: float,
    ) -> tuple[float, float]:
        turnover = 0.0
        for candidate in candidates:
            instrument = candidate.signal.instrument_id
            if instrument in holdings:
                continue
            if len(holdings) >= self._assumptions.maximum_positions:
                break
            if (
                candidate.entry_open is None
                or candidate.entry_amount_cny is None
                or candidate.entry_buy_state != "tradable"
            ):
                _reject(events, candidate, trade_date, "buy_not_tradable")
                continue
            if (
                candidate.target_exit_date is None
                or candidate.exit_date is None
                or candidate.exit_open is None
            ):
                _reject(events, candidate, trade_date, "exit_outside_sealed_window")
                continue
            price = candidate.entry_open * (1 + self._assumptions.slippage_bps / 10_000)
            budget = min(
                cash,
                self._assumptions.initial_cash_cny * self._assumptions.maximum_position_weight,
                candidate.entry_amount_cny * self._assumptions.maximum_order_participation,
            )
            quantity = _board_lots(budget / price, self._assumptions.lot_size)
            fee = _commission(quantity * price, self._assumptions)
            while quantity > 0 and quantity * price + fee > cash:
                quantity -= self._assumptions.lot_size
                fee = _commission(quantity * price, self._assumptions)
            if quantity <= 0:
                _reject(events, candidate, trade_date, "cash_or_liquidity_below_one_lot")
                continue
            amount = quantity * price
            cash -= amount + fee
            holdings[instrument] = _Holding(candidate, quantity, price, fee)
            events.append(
                BacktestEvent(
                    "filled_buy",
                    instrument,
                    candidate.signal.signal_date,
                    trade_date,
                    quantity,
                    price,
                    amount,
                    "next_open",
                )
            )
            turnover += amount
        return cash, turnover

    def _exits(
        self,
        trade_date: date,
        holdings: dict[str, _Holding],
        events: list[BacktestEvent],
        trades: list[ClosedTrade],
        cash: float,
    ) -> tuple[float, float]:
        turnover = 0.0
        for instrument, holding in tuple(holdings.items()):
            candidate = holding.candidate
            if candidate.target_exit_date == trade_date and candidate.exit_date != trade_date:
                events.append(
                    BacktestEvent(
                        "rejected_sell",
                        instrument,
                        candidate.signal.signal_date,
                        trade_date,
                        holding.quantity,
                        None,
                        0,
                        "sell_not_tradable_deferred",
                    )
                )
            if candidate.exit_date != trade_date:
                continue
            assert candidate.exit_open is not None
            price = candidate.exit_open * (1 - self._assumptions.slippage_bps / 10_000)
            amount = holding.quantity * price
            fee = _commission(amount, self._assumptions)
            tax = amount * self._assumptions.stamp_duty_rate
            cash += amount - fee - tax
            cost = holding.quantity * holding.entry_price + holding.entry_fee
            profit = amount - fee - tax - cost
            trades.append(
                ClosedTrade(
                    instrument,
                    candidate.entry_date,
                    trade_date,
                    holding.quantity,
                    holding.entry_price,
                    price,
                    profit,
                    profit / cost,
                )
            )
            events.append(
                BacktestEvent(
                    "filled_sell",
                    instrument,
                    candidate.signal.signal_date,
                    trade_date,
                    holding.quantity,
                    price,
                    amount,
                    "horizon_exit",
                )
            )
            del holdings[instrument]
            turnover += amount
        return cash, turnover

    def _equity_curve(
        self,
        *,
        dates: tuple[date, ...],
        instruments: tuple[str, ...],
        active_by_date: dict[date, dict[str, int]],
        cash_by_date: dict[date, float],
        start_date: date,
        end_date: date,
    ) -> tuple[EquityPoint, ...]:
        prices = self._source.prices(
            instruments=instruments, start_date=start_date, end_date=end_date
        )
        exact = {(price.trade_date, price.instrument_id): price.close for price in prices}
        last: dict[str, float] = {}
        curve = []
        for trade_date in dates:
            active = active_by_date[trade_date]
            market_value = 0.0
            for instrument, quantity in active.items():
                price = exact.get((trade_date, instrument), last.get(instrument))
                if price is None:
                    raise ValueError(f"持仓缺少可用估值价格：{instrument}@{trade_date}")
                last[instrument] = price
                market_value += quantity * price
            curve.append(
                EquityPoint(
                    trade_date,
                    cash_by_date[trade_date] + market_value,
                    cash_by_date[trade_date],
                    len(active),
                )
            )
        return tuple(curve)


def _board_lots(shares: float, lot_size: int) -> int:
    return max(0, int(shares // lot_size) * lot_size)


def _commission(amount: float, assumptions: BacktestAssumptions) -> float:
    if amount <= 0:
        return 0.0
    return max(assumptions.minimum_commission_cny, amount * assumptions.commission_rate)


def _reject(
    events: list[BacktestEvent],
    candidate: ReplayCandidate,
    execution_date: date,
    reason: str,
) -> None:
    events.append(
        BacktestEvent(
            "rejected_buy",
            candidate.signal.instrument_id,
            candidate.signal.signal_date,
            execution_date,
            0,
            None,
            0,
            reason,
        )
    )


__all__ = ["SealedReplayRunner"]
