import { useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";

import type { Candle } from "./candleFixture";
import { PriceChart } from "./PriceChart";
import { RangeSelector } from "./RangeSelector";
import type { IndustryHierarchyView } from "./rotationTypes";
import type { Indicator, MovingAverageWindow } from "./stockIndicators";

type Period = "day" | "week" | "month";

const periods: { key: Period; label: string }[] = [
  { key: "day", label: "日K" },
  { key: "week", label: "周K" },
  { key: "month", label: "月K" },
];
const windows: MovingAverageWindow[] = [5, 10, 30, 60, 120];
const indicators: Indicator[] = ["MACD", "RSI", "KDJ"];

export function StockPriceWorkbench({
  view,
  updatingLabel,
  onHoverDate,
}: {
  view: IndustryHierarchyView;
  updatingLabel?: string;
  onHoverDate: (date: string) => void;
}) {
  const [period, setPeriod] = useState<Period>(() => readPeriod());
  const [maWindows, setMaWindows] = useState<MovingAverageWindow[]>(() => readWindows());
  const [indicator, setIndicator] = useState<Indicator>(() => readIndicator());
  const candles = useMemo(
    () => selectCandles(view, period),
    [period, view],
  );
  const cutoffCandle = useMemo(
    () => selectCandles(view, "day").at(-1),
    [view],
  );
  const [range, setRange] = useState<[number, number]>(() => initialRange(candles.length));
  useEffect(() => {
    setRange(initialRange(candles.length));
  }, [candles.length, period, view.selected_code]);
  useEffect(() => {
    const url = new URL(window.location.href);
    url.searchParams.set("stock_period", period);
    url.searchParams.set("stock_indicator", indicator.toLowerCase());
    url.searchParams.set("stock_ma", maWindows.join(","));
    window.history.replaceState(null, "", url);
  }, [indicator, maWindows, period]);
  const selected = view.stock_evidence;
  return <section className="stock-price-workbench" aria-label="个股价格与技术指标">
    {updatingLabel ? (
      <div className="stock-local-loading" role="status">
        <span className="stock-loading-mark" aria-hidden="true" />
        <strong>{updatingLabel}</strong>
        <small>正在读取同一快照的 K 线与指标</small>
      </div>
    ) : null}
    <header>
      <div>
        <p className="eyebrow">价格事实</p>
        <h2>{selected?.instrument_name ?? "未选择股票"}</h2>
        <code>{selected?.instrument_id ?? "—"}</code>
        <small>{view.as_of} · 前复权研究视图</small>
      </div>
      <ControlGroup label="周期">
        {periods.map((item) => <Toggle
          active={period === item.key}
          key={item.key}
          label={item.label}
          onClick={() => setPeriod(item.key)}
        />)}
      </ControlGroup>
      <ControlGroup label="均线">
        {windows.map((window) => <Toggle
          active={maWindows.includes(window)}
          key={window}
          label={`MA${window}`}
          onClick={() => setMaWindows((current) =>
            current.includes(window)
              ? current.filter((item) => item !== window)
              : [...current, window].sort((left, right) => left - right))}
        />)}
      </ControlGroup>
      <ControlGroup label="副图">
        {indicators.map((item) => <Toggle
          active={indicator === item}
          key={item}
          label={item}
          onClick={() => setIndicator(item)}
        />)}
      </ControlGroup>
    </header>
    {candles.length ? <>
      <PriceChart
        candles={candles}
        cutoffCandle={cutoffCandle}
        indicator={indicator}
        maWindows={maWindows}
        visibleRange={range}
        onHoverDate={onHoverDate}
      />
      <RangeSelector
        count={candles.length}
        end={range[1]}
        endLabel={candles[range[1]]?.time ?? "—"}
        onChange={(start, end) => setRange([start, end])}
        start={range[0]}
        startLabel={candles[range[0]]?.time ?? "—"}
      />
      <p className="stock-chart-note">
        成交量固定；副图单选。周/月线按证据截止裁剪后聚合，均线与指标按所选周期重算。
      </p>
    </> : <div className="stock-chart-empty">所选周期没有足够的已完成 K 线。</div>}
  </section>;
}

function ControlGroup({ label, children }: { label: string; children: ReactNode }) {
  return <fieldset className="stock-chart-controls"><legend>{label}</legend>{children}</fieldset>;
}

function Toggle({
  active,
  label,
  onClick,
}: {
  active: boolean;
  label: string;
  onClick: () => void;
}) {
  return <button aria-pressed={active} onClick={onClick} type="button">{label}</button>;
}

function selectCandles(view: IndustryHierarchyView, period: Period): Candle[] {
  const source = period === "day"
    ? view.candles
    : period === "week" ? view.weekly_candles : view.monthly_candles;
  return source.map((item) => ({
    time: item.trade_date,
    open: item.open,
    high: item.high,
    low: item.low,
    close: item.close,
    volume: item.volume_lots,
    amount: item.amount_cny,
  }));
}

function initialRange(length: number): [number, number] {
  return [Math.max(0, length - 120), Math.max(0, length - 1)];
}

function readPeriod(): Period {
  const value = new URLSearchParams(window.location.search).get("stock_period");
  return value === "week" || value === "month" ? value : "day";
}

function readIndicator(): Indicator {
  const value = new URLSearchParams(window.location.search)
    .get("stock_indicator")?.toUpperCase();
  return value === "RSI" || value === "KDJ" ? value : "MACD";
}

function readWindows(): MovingAverageWindow[] {
  const values = new URLSearchParams(window.location.search)
    .get("stock_ma")?.split(",").map(Number) ?? [5, 10, 30];
  const valid = values.filter((value): value is MovingAverageWindow =>
    windows.includes(value as MovingAverageWindow));
  return valid.length ? [...new Set(valid)] : [5, 10, 30];
}
