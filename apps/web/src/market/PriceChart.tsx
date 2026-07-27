import { useEffect, useRef, useState } from "react";
import {
  CandlestickSeries,
  ColorType,
  createChart,
  HistogramSeries,
  LineSeries,
  type CandlestickData,
  type Time,
} from "lightweight-charts";

import type { Candle } from "./candleFixture";

type PriceChartProps = {
  candles: Candle[];
};

type Hover = Candle | null;

export function PriceChart({ candles }: PriceChartProps) {
  const container = useRef<HTMLDivElement>(null);
  const [hover, setHover] = useState<Hover>(candles.at(-1) ?? null);

  useEffect(() => {
    if (!container.current || typeof ResizeObserver === "undefined") return;
    const chart = createChart(container.current, {
      autoSize: true,
      height: 500,
      layout: {
        background: { type: ColorType.Solid, color: "#ffffff" },
        textColor: "#52606a",
        fontFamily: '"IBM Plex Sans", "Noto Sans SC", sans-serif',
      },
      grid: {
        vertLines: { color: "#edf0ef" },
        horzLines: { color: "#edf0ef" },
      },
      rightPriceScale: { borderColor: "#d9dfdc" },
      timeScale: { borderColor: "#d9dfdc", rightOffset: 2 },
      crosshair: { vertLine: { color: "#5677a6" }, horzLine: { color: "#5677a6" } },
    });
    const prices = chart.addSeries(CandlestickSeries, {
      upColor: "#c23b32",
      downColor: "#148060",
      borderUpColor: "#c23b32",
      borderDownColor: "#148060",
      wickUpColor: "#c23b32",
      wickDownColor: "#148060",
    });
    const volume = chart.addSeries(
      HistogramSeries,
      { priceFormat: { type: "volume" }, priceScaleId: "" },
      1,
    );
    const ma5 = chart.addSeries(LineSeries, { color: "#315f99", lineWidth: 2 });
    const ma20 = chart.addSeries(LineSeries, { color: "#b47b20", lineWidth: 2 });
    prices.setData(candles);
    volume.setData(
      candles.map((item) => ({
        time: item.time,
        value: item.volume,
        color: item.close >= item.open ? "#c23b3270" : "#14806070",
      })),
    );
    ma5.setData(movingAverage(candles, 5));
    ma20.setData(movingAverage(candles, 20));
    chart.panes()[0]?.setStretchFactor(4);
    chart.panes()[1]?.setStretchFactor(1);
    chart.timeScale().fitContent();
    chart.subscribeCrosshairMove((parameter) => {
      const item = parameter.seriesData.get(prices) as CandlestickData<Time> | undefined;
      const time = typeof item?.time === "string" ? item.time : null;
      setHover(time ? (candles.find((candle) => candle.time === time) ?? null) : null);
    });
    return () => chart.remove();
  }, [candles]);

  return (
    <div className="chart-shell" data-max-date={candles.at(-1)?.time ?? ""}>
      <div className="chart-legend" aria-live="polite">
        <strong>{hover?.time ?? "移动指针查看"}</strong>
        <span>开 {format(hover?.open)}</span>
        <span>高 {format(hover?.high)}</span>
        <span>低 {format(hover?.low)}</span>
        <span>收 {format(hover?.close)}</span>
        <span>量 {hover ? `${(hover.volume / 10_000).toFixed(0)} 万` : "—"}</span>
      </div>
      <div ref={container} className="chart-canvas" aria-label="统一 K 线与成交量图" />
    </div>
  );
}

function movingAverage(candles: Candle[], window: number) {
  return candles.flatMap((candle, index) => {
    if (index + 1 < window) return [];
    const slice = candles.slice(index + 1 - window, index + 1);
    return [
      {
        time: candle.time,
        value: slice.reduce((total, item) => total + item.close, 0) / window,
      },
    ];
  });
}

function format(value: number | undefined): string {
  return value === undefined ? "—" : value.toFixed(2);
}
