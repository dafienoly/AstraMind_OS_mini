import { useEffect, useRef, useState } from "react";
import {
  CandlestickSeries,
  ColorType,
  createChart,
  HistogramSeries,
  LineSeries,
  LineStyle,
  type CandlestickData,
  type Time,
} from "lightweight-charts";

import type { Candle } from "./candleFixture";
import {
  indicatorValues,
  movingAverage,
  returnToCutoff,
  type Indicator,
} from "./stockIndicators";

type PriceChartProps = {
  candles: Candle[];
  cutoffCandle?: Candle;
  maWindows?: number[];
  indicator?: Indicator | null;
  visibleRange?: [number, number];
  onHoverDate?: (date: string) => void;
};

type Hover = {
  candle: Candle;
  averages: Record<number, number>;
  indicator: Record<string, number>;
} | null;

const maColors = ["#315f99", "#b47a22", "#6d7e68", "#8b5b82", "#377f93"];
const indicatorColors = ["#2e5e84", "#b47a22", "#8b5b82"];
const defaultMaWindows = [5, 20];

export function PriceChart({
  candles,
  cutoffCandle,
  maWindows = defaultMaWindows,
  indicator = null,
  visibleRange,
  onHoverDate,
}: PriceChartProps) {
  const container = useRef<HTMLDivElement>(null);
  const [hover, setHover] = useState<Hover>(null);

  useEffect(() => {
    if (!container.current || typeof ResizeObserver === "undefined") return;
    const averages = new Map<number, Map<string, number>>();
    for (const window of maWindows) {
      averages.set(window, new Map(
        movingAverage(candles, window).map((point) => [point.time, point.value]),
      ));
    }
    const study = indicator ? indicatorValues(candles, indicator) : [];
    const studyByTime = new Map(study.map((point) => [point.time, point.values]));
    const hoverAt = (candle: Candle | undefined): Hover => candle ? {
      candle,
      averages: Object.fromEntries(maWindows.flatMap((window) => {
        const value = averages.get(window)?.get(candle.time);
        return value === undefined ? [] : [[window, value]];
      })),
      indicator: studyByTime.get(candle.time) ?? {},
    } : null;
    setHover(hoverAt(candles.at(-1)));
    onHoverDate?.(cutoffCandle?.time ?? candles.at(-1)?.time ?? "");

    const chart = createChart(container.current, {
      autoSize: true,
      height: indicator ? 660 : 500,
      layout: {
        background: { type: ColorType.Solid, color: "#ffffff" },
        textColor: "#52606a",
        fontFamily: '"IBM Plex Sans", "Noto Sans SC", sans-serif',
        panes: { separatorColor: "#d9dfdc", separatorHoverColor: "#8da3b1" },
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
    prices.setData(candles);
    volume.setData(candles.map((item) => ({
      time: item.time,
      value: item.volume,
      color: item.close >= item.open ? "#c23b3270" : "#14806070",
    })));
    maWindows.forEach((window, index) => {
      const series = chart.addSeries(LineSeries, {
        color: maColors[index % maColors.length],
        lineWidth: 2,
        title: `MA${window}`,
      });
      series.setData(movingAverage(candles, window));
    });
    if (indicator) addIndicator(chart, indicator, study);
    chart.panes()[0]?.setStretchFactor(5);
    chart.panes()[1]?.setStretchFactor(1.15);
    chart.panes()[2]?.setStretchFactor(1.8);
    if (visibleRange && candles[visibleRange[0]] && candles[visibleRange[1]]) {
      chart.timeScale().setVisibleRange({
        from: candles[visibleRange[0]].time,
        to: candles[visibleRange[1]].time,
      });
    } else {
      chart.timeScale().fitContent();
    }
    const byTime = new Map(candles.map((candle) => [candle.time, candle]));
    chart.subscribeCrosshairMove((parameter) => {
      const item = parameter.seriesData.get(prices) as CandlestickData<Time> | undefined;
      const time = typeof item?.time === "string" ? item.time : null;
      setHover(hoverAt(time ? byTime.get(time) : undefined));
      onHoverDate?.(time ?? cutoffCandle?.time ?? candles.at(-1)?.time ?? "");
    });
    return () => chart.remove();
  }, [candles, cutoffCandle, indicator, maWindows, onHoverDate, visibleRange]);

  const cutoff = cutoffCandle ?? candles.at(-1);
  return (
    <div className="chart-shell" data-max-date={cutoff?.time ?? ""}>
      <PriceChartLegend cutoff={cutoff} hover={hover} />
      <div ref={container} className="chart-canvas" aria-label="统一 K 线、成交量与技术指标图" />
    </div>
  );
}

function PriceChartLegend({ cutoff, hover }: { cutoff?: Candle; hover: Hover }) {
  const cutoffReturn = hover && cutoff
    ? returnToCutoff(hover.candle.close, cutoff.close)
    : null;
  return <>
    <div className="chart-legend" aria-live="polite">
      <strong>{hover?.candle.time ?? "移动指针查看"}</strong>
      <span>开 {format(hover?.candle.open)}</span>
      <span>高 {format(hover?.candle.high)}</span>
      <span>低 {format(hover?.candle.low)}</span>
      <span>收 {format(hover?.candle.close)}</span>
      <span>量 {formatVolume(hover?.candle.volume)}</span>
      <span>额 {formatAmount(hover?.candle.amount)}</span>
      {cutoffReturn !== null && cutoff ? (
        <strong className={cutoffReturn >= 0 ? "return-up" : "return-down"}>
          至 {cutoff.time} {formatPercent(cutoffReturn)}
        </strong>
      ) : null}
    </div>
    <div className="chart-study-legend">
      {Object.entries(hover?.averages ?? {}).map(([window, value]) => (
        <span key={window}>MA{window} {value.toFixed(2)}</span>
      ))}
      {Object.entries(hover?.indicator ?? {}).map(([name, value]) => (
        <span key={name}>{name} {value.toFixed(2)}</span>
      ))}
    </div>
  </>;
}

function addIndicator(
  chart: ReturnType<typeof createChart>,
  indicator: Indicator,
  points: ReturnType<typeof indicatorValues>,
) {
  if (indicator === "MACD") {
    const histogram = chart.addSeries(HistogramSeries, {
      title: "MACD",
      priceScaleId: "",
    }, 2);
    histogram.setData(points.map((point) => ({
      time: point.time,
      value: point.values.MACD,
      color: point.values.MACD >= 0 ? "#c23b3270" : "#14806070",
    })));
    addStudyLine(chart, points, "DIF", 0);
    addStudyLine(chart, points, "DEA", 1);
    return;
  }
  const names = indicator === "RSI" ? ["RSI"] : ["K", "D", "J"];
  names.forEach((name, index) => addStudyLine(chart, points, name, index));
  if (indicator === "RSI") {
    for (const level of [30, 70]) {
      const line = chart.addSeries(LineSeries, {
        color: "#9ba6a1",
        lineWidth: 1,
        lineStyle: LineStyle.Dashed,
        title: String(level),
      }, 2);
      line.setData(points.map((point) => ({ time: point.time, value: level })));
    }
  }
}

function addStudyLine(
  chart: ReturnType<typeof createChart>,
  points: ReturnType<typeof indicatorValues>,
  name: string,
  colorIndex: number,
) {
  const series = chart.addSeries(LineSeries, {
    color: indicatorColors[colorIndex % indicatorColors.length],
    lineWidth: 2,
    title: name,
  }, 2);
  series.setData(points.map((point) => ({ time: point.time, value: point.values[name] })));
}

function format(value: number | undefined): string {
  return value === undefined ? "—" : value.toFixed(2);
}

function formatVolume(value: number | undefined) {
  return value === undefined ? "—" : `${(value / 10_000).toFixed(1)} 万手`;
}

function formatAmount(value: number | null | undefined) {
  return value == null ? "—" : `${(value / 100_000_000).toFixed(2)} 亿元`;
}

function formatPercent(value: number) {
  return `${value >= 0 ? "+" : ""}${(value * 100).toFixed(2)}% ${value >= 0 ? "↑" : "↓"}`;
}
