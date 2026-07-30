import {
  useEffect, useMemo, useState,
  type Dispatch, type SetStateAction,
} from "react";

import { fetchRealtimeBarWindow } from "../market-dashboard/marketDashboardClient";
import { RealtimeMinuteChart } from "../market-dashboard/realtime/RealtimeMinuteChart";
import { RealtimeOrderBook } from "../market-dashboard/realtime/RealtimeOrderBook";
import type {
  PriceCandle,
  RealtimeInstrumentQuote,
  RealtimeIndicatorPoint,
  RealtimeMinuteBar,
} from "../market-dashboard/types";
import { PriceChart } from "../market/PriceChart";
import { RangeSelector } from "../market/RangeSelector";
import { aggregateCandles, type Candle } from "../market/candleFixture";
import {
  HistoryWindowSelector,
  type PriceHistoryWindow,
  type PriceInstrumentType,
  usePriceHistory,
} from "../market/priceHistory";

type Period = "minute" | "day" | "week" | "month" | "year";
const minuteFrequencies = [1, 5, 15, 30, 60, 120] as const;

export function SecurityMarketInspector({
  instrumentId,
  instrumentName,
  instrumentType,
  dataSnapshotId,
  evidenceCutoff,
  completed,
  realtime,
}: {
  instrumentId: string;
  instrumentName: string;
  instrumentType: PriceInstrumentType;
  dataSnapshotId: string;
  evidenceCutoff: string;
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
  const [historyWindow, setHistoryWindow] = useState<PriceHistoryWindow>("one_year");
  const [minuteFrequency, setMinuteFrequency] = useState(1);
  const [minuteSessions, setMinuteSessions] = useState(1);
  const minute = useMinuteWindow(
    instrumentId, period, minuteFrequency, minuteSessions, realtime?.minutes ?? [],
  );
  useEffect(() => setHistoryWindow("one_year"), [instrumentId]);
  const history = usePriceHistory({
    instrumentType,
    instrumentId,
    dataSnapshotId,
    evidenceCutoff,
    window: historyWindow,
    fallback: completed.daily,
  });
  const candles = useMemo(
    () => {
      if (period === "minute") return [];
      const daily = toCandles(history.bars);
      if (historyWindow === "one_year") {
        return period === "day" ? daily
          : period === "week" ? toCandles(completed.weekly)
            : period === "month" ? toCandles(completed.monthly)
              : aggregateYear(daily);
      }
      return aggregateCandles(
        daily,
        period === "day" ? "日线" : period === "week" ? "周线" : "月线",
      );
    },
    [completed.monthly, completed.weekly, history.bars, historyWindow, period],
  );
  const [range, setRange] = useState<[number, number]>(() => initialRange(candles.length));
  useEffect(() => setRange(initialRange(candles.length)), [
    candles.length,
    instrumentId,
    period,
  ]);
  return <section className="security-market-inspector" aria-label="证券行情检查器">
    <InspectorHeader instrumentId={instrumentId} instrumentName={instrumentName}
      period={period} setPeriod={setPeriod} minuteFrequency={minuteFrequency}
      setMinuteFrequency={setMinuteFrequency} minuteSessions={minuteSessions}
      setMinuteSessions={setMinuteSessions} history={history}
      historyWindow={historyWindow} setHistoryWindow={setHistoryWindow} />
    <HistoryCoverageNote history={history} />
    <div className="security-market-layout">
      <div className="security-price-pane">
        {period === "minute" && minute.load === "loading" ? (
          <div className="security-market-empty">正在加载所选分钟窗口…</div>
        ) : period === "minute" && minute.bars.length ? (
          <>
          <RealtimeMinuteChart bars={minute.bars} indicators={minute.indicators}
            indicatorState={minute.indicatorState} instrumentId={instrumentId} />
          {minute.gaps.length ? <p className="history-coverage-note">
            分钟缺口 {minute.gaps.length} 个；不完整桶已失败关闭。
          </p> : <p className="history-coverage-note">
            {minute.bars.some((bar) => bar.lifecycle === "forming")
              ? "含形成中 Bar；闭合指标不使用该 Bar。"
              : "当前窗口仅含闭合或封存 Bar。"}
          </p>}
          {minute.load === "error" ? <p className="history-coverage-note">
            分钟历史加载失败；当前仅显示已有实时形成中数据。
          </p> : null}
          </>
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

function useMinuteWindow(
  instrumentId: string,
  period: Period,
  frequency: number,
  sessions: number,
  current: RealtimeMinuteBar[],
) {
  const [bars, setBars] = useState(current);
  const [indicatorState, setIndicatorState] = useState<"ready" | "insufficient_seed">(
    "insufficient_seed",
  );
  const [gaps, setGaps] = useState<string[]>([]);
  const [indicators, setIndicators] = useState<RealtimeIndicatorPoint[]>([]);
  const [load, setLoad] = useState<"loading" | "ready" | "error">("ready");
  useEffect(() => {
    if (period !== "minute") return;
    const controller = new AbortController();
    setLoad("loading");
    void fetchRealtimeBarWindow(instrumentId, frequency, sessions, controller.signal)
      .then((page) => {
        setBars(page.bars ?? []);
        setIndicatorState(page.indicator_state ?? "insufficient_seed");
        setGaps(page.known_gaps ?? []);
        setIndicators(page.indicators ?? []);
        setLoad("ready");
      }).catch(() => {
        setIndicatorState("insufficient_seed");
        if (!controller.signal.aborted) setLoad("error");
      });
    return () => controller.abort();
  }, [frequency, instrumentId, period, sessions]);
  useEffect(() => {
    if (!current.length) return;
    setBars((history) => {
      const values = new Map(history.map((row) => [row.minute, row]));
      for (const row of current) values.set(row.minute, row);
      return [...values.values()].sort((left, right) => left.minute.localeCompare(right.minute));
    });
  }, [current]);
  return { bars, gaps, indicators, indicatorState, load };
}

function InspectorHeader({
  instrumentId, instrumentName, period, setPeriod, minuteFrequency,
  setMinuteFrequency, minuteSessions, setMinuteSessions, history,
  historyWindow, setHistoryWindow,
}: {
  instrumentId: string;
  instrumentName: string;
  period: Period;
  setPeriod: Dispatch<SetStateAction<Period>>;
  minuteFrequency: number;
  setMinuteFrequency: Dispatch<SetStateAction<number>>;
  minuteSessions: number;
  setMinuteSessions: Dispatch<SetStateAction<number>>;
  history: ReturnType<typeof usePriceHistory>;
  historyWindow: PriceHistoryWindow;
  setHistoryWindow: Dispatch<SetStateAction<PriceHistoryWindow>>;
}) {
  return <header>
    <div><p className="eyebrow">统一证券行情内核</p><h2>{instrumentName}</h2>
      <code>{instrumentId}</code></div>
    <nav aria-label="行情周期">
      {([["minute", "分钟"], ["day", "日 K"], ["week", "周 K"],
        ["month", "月 K"], ["year", "年 K"]] as const).map(([value, label]) => (
        <button aria-pressed={period === value} key={value}
          onClick={() => setPeriod(value)} type="button">{label}</button>
      ))}
    </nav>
    {period === "minute" ? <div aria-label="分钟周期与窗口">
      {minuteFrequencies.map((value) => <button aria-pressed={minuteFrequency === value}
        key={value} onClick={() => setMinuteFrequency(value)}
        type="button">{value} 分钟</button>)}
      <button aria-pressed={minuteSessions === 5}
        onClick={() => setMinuteSessions((value) => value === 5 ? 1 : 5)}
        type="button">5 日</button>
    </div> : null}
    <HistoryWindowSelector onChange={(next) => {
      setHistoryWindow(next);
      if (period === "minute") setPeriod("day");
    }} state={history.kind} value={historyWindow} />
  </header>;
}

function HistoryCoverageNote({
  history,
}: {
  history: ReturnType<typeof usePriceHistory>;
}) {
  if (history.kind === "error") return <p className="history-coverage-note">
    {history.message}，继续显示近一年快照行情。
  </p>;
  if (history.kind !== "ready") return null;
  return <p className="history-coverage-note">
    实际覆盖 {history.page.coverage_start ?? "不可用"} 至 {
      history.page.coverage_end ?? "不可用"
    } · 当前快照与证据截止保持不变
  </p>;
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

function aggregateYear(values: Candle[]): Candle[] {
  const groups = new Map<string, Candle[]>();
  for (const value of values) {
    const key = value.time.slice(0, 4);
    groups.set(key, [...(groups.get(key) ?? []), value]);
  }
  return [...groups.values()].map((group) => ({
    time: group.at(-1)?.time ?? "",
    open: group[0].open,
    high: Math.max(...group.map((value) => value.high)),
    low: Math.min(...group.map((value) => value.low)),
    close: group.at(-1)?.close ?? group[0].close,
    volume: group.reduce((total, value) => total + value.volume, 0),
    amount: group.reduce((total, value) => total + (value.amount ?? 0), 0),
  }));
}
