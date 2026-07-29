import { useMemo, useState } from "react";

import {
  aggregateCandles,
  type Candle,
  type Timeframe,
} from "../market/candleFixture";
import { PriceChart } from "../market/PriceChart";
import { RangeSelector } from "../market/RangeSelector";
import type { MarketDashboardProjection } from "./types";
import type { RealtimeMarketView } from "./useRealtimeMarket";

const timeframes: Timeframe[] = ["日线", "周线", "月线"];

export function OverviewView({
  projection,
  realtime,
}: {
  projection: MarketDashboardProjection;
  realtime: RealtimeMarketView;
}) {
  const initial = projection.selected_index_id ?? projection.indexes[0]?.instrument_id ?? "";
  const [selectedId, setSelectedId] = useState(initial);
  const [timeframe, setTimeframe] = useState<Timeframe>("日线");
  const selected = projection.indexes.find((item) => item.instrument_id === selectedId)
    ?? projection.indexes[0];
  const daily = useMemo<Candle[]>(
    () => (selected?.candles ?? []).map((item) => ({
      time: item.trade_date,
      open: item.open,
      high: item.high,
      low: item.low,
      close: item.close,
      volume: item.volume_lots,
      amount: item.amount_cny,
    })),
    [selected],
  );
  const candles = useMemo(() => aggregateCandles(daily, timeframe), [daily, timeframe]);
  const [range, setRange] = useState<[number, number]>(() => [
    Math.max(0, candles.length - 100),
    Math.max(0, candles.length - 1),
  ]);
  const end = Math.min(range[1], Math.max(0, candles.length - 1));
  const start = Math.min(range[0], Math.max(0, end - 1));
  const visible = candles.slice(start, end + 1);
  const realtimeIndexes = useMemo(
    () => new Map(
      (realtime.projection?.indexes ?? []).map((item) => [item.instrument_id, item]),
    ),
    [realtime.projection?.indexes],
  );
  const liveSelected = selected
    ? realtimeIndexes.get(selected.instrument_id)
    : undefined;
  const liveReference = liveSelected ? {
    value: liveSelected.last_price,
    label: realtime.effectiveState === "current"
      ? "盘中临时"
      : realtime.effectiveState === "stale" ? "盘中陈旧" : "盘中断线",
    state: realtime.effectiveState,
  } : undefined;

  function switchPeriod(next: Timeframe) {
    const nextCandles = aggregateCandles(daily, next);
    setTimeframe(next);
    setRange([Math.max(0, nextCandles.length - 100), Math.max(0, nextCandles.length - 1)]);
  }

  function selectIndex(item: MarketDashboardProjection["indexes"][number]) {
    setSelectedId(item.instrument_id);
    const count = aggregateCandles(toCandles(item.candles), timeframe).length;
    setRange([Math.max(0, count - 100), Math.max(0, count - 1)]);
  }

  if (!selected || !projection.breadth || !projection.liquidity || !projection.regime) {
    return <DashboardBlocked gaps={projection.known_gaps} />;
  }
  return <>
    <IndexRibbon
      indexes={projection.indexes}
      realtime={realtime}
      realtimeIndexes={realtimeIndexes}
      selectedId={selected.instrument_id}
      onSelect={selectIndex}
    />
    <div className="market-overview-grid">
      <section className="market-price-sheet">
        <header className="market-sheet-heading">
          <div>
            <p className="eyebrow">宽基价格结构 / {selected.instrument_id}</p>
            <h1>{selected.instrument_name}</h1>
            <p>价格结构与全市场参与共同解释，不由一张 K 线单独判断。</p>
          </div>
          <div className="timeframe" aria-label="K 线周期">
            {timeframes.map((item) => (
              <button className={item === timeframe ? "active" : ""} key={item}
                onClick={() => switchPeriod(item)} type="button">{item}</button>
            ))}
          </div>
        </header>
        <PriceChart candles={visible} liveReference={liveReference} />
        <RangeSelector
          count={candles.length}
          start={start}
          end={end}
          startLabel={candles[start]?.time ?? "—"}
          endLabel={candles[end]?.time ?? "—"}
          onChange={(nextStart, nextEnd) => setRange([nextStart, nextEnd])}
        />
      </section>
      <MarketInspector projection={projection} realtime={realtime} selected={selected} />
    </div>
  </>;
}

function IndexRibbon({
  indexes,
  realtime,
  realtimeIndexes,
  selectedId,
  onSelect,
}: {
  indexes: MarketDashboardProjection["indexes"];
  realtime: RealtimeMarketView;
  realtimeIndexes: Map<string, NonNullable<RealtimeMarketView["projection"]>["indexes"][number]>;
  selectedId: string;
  onSelect: (item: MarketDashboardProjection["indexes"][number]) => void;
}) {
  return <section className="market-index-ribbon" aria-label="宽基指数">
    {indexes.map((item) => {
      const live = realtimeIndexes.get(item.instrument_id);
      const price = live?.last_price ?? item.latest_close;
      const change = live?.change_percent ?? item.percent_change;
      return <button aria-pressed={item.instrument_id === selectedId}
        key={item.instrument_id} onClick={() => onSelect(item)} type="button">
        <span>{item.instrument_name}</span>
        <strong>{price.toFixed(2)}</strong>
        <em data-direction={change >= 0 ? "up" : "down"}>
          {signed(change)}% {change >= 0 ? "↑" : "↓"}
        </em>
        {live ? <small data-state={realtime.effectiveState}>
          {realtime.effectiveState === "current"
            ? "盘中临时"
            : realtime.effectiveState === "stale" ? "盘中陈旧" : "盘中断线"}
        </small> : null}
      </button>;
    })}
  </section>;
}

function MarketInspector({
  projection,
  realtime,
  selected,
}: {
  projection: MarketDashboardProjection;
  realtime: RealtimeMarketView;
  selected: MarketDashboardProjection["indexes"][number];
}) {
  const breadth = projection.breadth!;
  const liquidity = projection.liquidity!;
  const regime = projection.regime!;
  const live = realtime.projection;
  const liveIndex = live?.indexes.find(
    (item) => item.instrument_id === selected.instrument_id,
  );
  return <aside className="market-inspector">
    <p className="eyebrow">市场状态检查器</p>
    <h2>{regime.label}</h2>
    <span className={`regime-mark regime-mark--${regime.state}`}>
      置信度 {(regime.confidence * 100).toFixed(0)}%
    </span>
    <section className="realtime-inspector" data-state={realtime.effectiveState}>
      <small>盘中临时观察 · 不改写正式状态</small>
      <strong>{liveIndex
        ? `${selected.instrument_name} ${liveIndex.last_price.toFixed(2)}`
        : "等待所选指数实时行情"}</strong>
      <dl>
        <div><dt>上涨 / 下跌 / 平盘</dt><dd>{live
          ? `${live.advancing} ↑ / ${live.declining} ↓ / ${live.unchanged} —`
          : "—"}</dd></div>
        <div><dt>盘中累计成交额</dt><dd>{live ? formatAmount(live.total_amount) : "—"}</dd></div>
      </dl>
    </section>
    <dl>
      <div><dt>上涨 / 下跌</dt><dd>{breadth.advancing} ↑ / {breadth.declining} ↓</dd></div>
      <div><dt>250 日新高 / 新低</dt><dd>{breadth.new_high_250d} / {breadth.new_low_250d}</dd></div>
      <div><dt>涨停 / 跌停锁定</dt><dd>{breadth.upper_limit_locked} / {breadth.lower_limit_locked}</dd></div>
      <div><dt>全市场成交额</dt><dd>{formatAmount(liquidity.amount_cny)}</dd></div>
      <div><dt>成交额相对 20 日</dt><dd>{formatRatio(liquidity.amount_change_20d)}</dd></div>
      <div><dt>{selected.instrument_name} 20 日</dt><dd>{formatRatio(selected.return_20d)}</dd></div>
      <div><dt>250 日回撤</dt><dd>{formatRatio(selected.drawdown_250d)}</dd></div>
    </dl>
    <section>
      <small>判定依据</small>
      {regime.observations.map((item) => <p key={item}>{item}</p>)}
    </section>
    <details>
      <summary>数据与方法</summary>
      <p>{regime.definition_version}</p>
      <code>{projection.data_snapshot_id}</code>
    </details>
  </aside>;
}

export function DashboardBlocked({ gaps }: { gaps: string[] }) {
  return <section className="market-blocked">
    <p className="eyebrow">市场证据已阻断</p>
    <h1>当前快照不能形成一致的大盘判断</h1>
    <p>缺少宽基、行业或成员覆盖时不显示演示数据。请先恢复日度数据管线。</p>
    <code>{gaps.join(" · ") || "projection_incomplete"}</code>
    <a href="/system">查看数据恢复状态</a>
  </section>;
}

function signed(value: number) {
  return `${value >= 0 ? "+" : ""}${value.toFixed(2)}`;
}

function formatAmount(value: number) {
  return `${(value / 100_000_000_000).toFixed(2)} 千亿元`;
}

function formatRatio(value: number | null) {
  return value === null ? "—" : `${value >= 0 ? "+" : ""}${(value * 100).toFixed(1)}%`;
}

function toCandles(candles: MarketDashboardProjection["indexes"][number]["candles"]): Candle[] {
  return candles.map((candle) => ({
    time: candle.trade_date,
    open: candle.open,
    high: candle.high,
    low: candle.low,
    close: candle.close,
    volume: candle.volume_lots,
    amount: candle.amount_cny,
  }));
}
