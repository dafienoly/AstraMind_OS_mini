import { useEffect, useMemo, useState } from "react";

import { RealtimeMinuteChart } from "../market-dashboard/realtime/RealtimeMinuteChart";
import { RealtimeOrderBook } from "../market-dashboard/realtime/RealtimeOrderBook";
import type {
  PriceCandle,
  RealtimeInstrumentQuote,
  RealtimeMinuteBar,
} from "../market-dashboard/types";
import { PriceChart } from "../market/PriceChart";
import { RangeSelector } from "../market/RangeSelector";
import type { Candle } from "../market/candleFixture";

type Period = "minute" | "day" | "week" | "month";

export function SecurityMarketInspector({
  instrumentId,
  instrumentName,
  completed,
  realtime,
}: {
  instrumentId: string;
  instrumentName: string;
  completed: {
    daily: PriceCandle[];
    weekly: PriceCandle[];
    monthly: PriceCandle[];
  };
  realtime: {
    state: "current" | "stale" | "disconnected";
    quote: RealtimeInstrumentQuote | null;
    minutes: RealtimeMinuteBar[];
  } | null;
}) {
  const [period, setPeriod] = useState<Period>(
    () => realtime?.minutes.length ? "minute" : "day",
  );
  const candles = useMemo(
    () => period === "day" ? toCandles(completed.daily)
      : period === "week" ? toCandles(completed.weekly)
        : period === "month" ? toCandles(completed.monthly) : [],
    [completed, period],
  );
  const [range, setRange] = useState<[number, number]>(() => initialRange(candles.length));
  useEffect(() => setRange(initialRange(candles.length)), [
    candles.length,
    instrumentId,
    period,
  ]);
  return <section className="security-market-inspector" aria-label="证券行情检查器">
    <header>
      <div>
        <p className="eyebrow">统一证券行情内核</p>
        <h2>{instrumentName}</h2>
        <code>{instrumentId}</code>
      </div>
      <nav aria-label="行情周期">
        <button aria-pressed={period === "minute"} disabled={!realtime?.minutes.length}
          onClick={() => setPeriod("minute")} type="button">1 分钟</button>
        <button aria-pressed={period === "day"} onClick={() => setPeriod("day")}
          type="button">日 K</button>
        <button aria-pressed={period === "week"} onClick={() => setPeriod("week")}
          type="button">周 K</button>
        <button aria-pressed={period === "month"} onClick={() => setPeriod("month")}
          type="button">月 K</button>
      </nav>
    </header>
    <div className="security-market-layout">
      <div className="security-price-pane">
        {period === "minute" && realtime?.minutes.length ? (
          <RealtimeMinuteChart bars={realtime.minutes} instrumentId={instrumentId} />
        ) : candles.length ? <>
          <PriceChart
            candles={candles}
            indicator="MACD"
            maWindows={[5, 10, 30, 60]}
            visibleRange={range}
            liveReference={realtime?.quote?.last_price ? {
              value: realtime.quote.last_price,
              label: "盘中临时",
              state: realtime.state,
            } : undefined}
          />
          <RangeSelector
            count={candles.length}
            end={range[1]}
            endLabel={candles[range[1]]?.time ?? "—"}
            onChange={(start, end) => setRange([start, end])}
            start={range[0]}
            startLabel={candles[range[0]]?.time ?? "—"}
          />
        </> : <div className="security-market-empty">所选周期没有可用行情。</div>}
      </div>
      <RealtimeOrderBook quote={realtime?.quote ?? null} />
    </div>
  </section>;
}

function toCandles(values: PriceCandle[]): Candle[] {
  return values.map((value) => ({
    time: value.trade_date,
    open: value.open,
    high: value.high,
    low: value.low,
    close: value.close,
    volume: value.volume_lots,
    amount: value.amount_cny,
  }));
}

function initialRange(length: number): [number, number] {
  return [Math.max(0, length - 120), Math.max(0, length - 1)];
}
