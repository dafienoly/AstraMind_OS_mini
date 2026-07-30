import {
  CandlestickSeries,
  ColorType,
  createChart,
  HistogramSeries,
  LineSeries,
  type IChartApi,
  type ISeriesApi,
  type Time,
} from "lightweight-charts";
import { useEffect, useRef, useState, type RefObject } from "react";

import type { RealtimeIndicatorPoint, RealtimeMinuteBar } from "../types";

export function RealtimeMinuteChart({
  instrumentId,
  bars,
  indicatorState = "ready",
  indicators = [],
  frequency = 1,
}: {
  instrumentId: string;
  bars: RealtimeMinuteBar[];
  indicatorState?: "ready" | "insufficient_seed";
  indicators?: RealtimeIndicatorPoint[];
  frequency?: number;
}) {
  const host = useRef<HTMLDivElement>(null);
  const { chart, candle, volume, amount, maLines, macd, dif, dea } = useChartSeries(host);
  const [crosshairText, setCrosshairText] = useState("移动十字光标查看该分钟明细");
  const forming = bars.find((row) => (
    row.lifecycle === "forming" && !row.is_complete && row.known_gaps.length === 0
  ));

  useEffect(() => {
    if (!candle.current || !volume.current || !amount.current) return;
    const drawable = bars.filter((row) => (
      row.is_complete && row.known_gaps.length === 0
      && (row.lifecycle === "closed" || row.lifecycle === "sealed")
    ));
    const values = drawable.map((row) => ({
      time: toTime(row.minute),
      open: row.open,
      high: row.high,
      low: row.low,
      close: row.close,
    }));
    const volumes = drawable.map((row) => ({
      time: toTime(row.minute),
      value: row.volume,
      color: row.close >= row.open ? "#b2483f66" : "#2f7c6866",
    }));
    const amounts = drawable.map((row) => ({
      time: toTime(row.minute),
      value: row.amount,
      color: "#59636b55",
    }));
    candle.current.setData(values);
    volume.current.setData(volumes);
    amount.current.setData(amounts);
    chart.current?.timeScale().fitContent();
  }, [bars, instrumentId]);

  useEffect(() => {
    const fields = ["ma5", "ma10", "ma30", "ma60"] as const;
    maLines.current.forEach((series, index) => {
      const field = fields[index];
      series.setData(indicators.flatMap((row) => (
        row[field] == null ? [] : [{ time: toTime(row.minute), value: row[field] }]
      )));
    });
    macd.current?.setData(indicators.flatMap((row) => (
      row.histogram == null ? [] : [{
        time: toTime(row.minute),
        value: row.histogram,
        color: row.histogram >= 0 ? "#b2483f66" : "#2f7c6866",
      }]
    )));
    dif.current?.setData(indicators.flatMap((row) => (
      row.macd == null ? [] : [{ time: toTime(row.minute), value: row.macd }]
    )));
    dea.current?.setData(indicators.flatMap((row) => (
      row.signal == null ? [] : [{ time: toTime(row.minute), value: row.signal }]
    )));
  }, [indicators]);

  useEffect(() => {
    const currentChart = chart.current;
    if (!currentChart) return;
    const handler = ({ time }: { time?: Time }) => {
      if (time == null) return;
      const timestamp = Number(time);
      const bar = bars.find((row) => Number(toTime(row.minute)) === timestamp);
      const point = indicators.find((row) => Number(toTime(row.minute)) === timestamp);
      if (!bar) return;
      setCrosshairText([
        `O ${bar.open} H ${bar.high} L ${bar.low} C ${bar.close}`,
        `量 ${bar.volume} 额 ${bar.amount}`,
        `MA ${point?.ma5 ?? "—"}/${point?.ma10 ?? "—"}/${point?.ma30 ?? "—"}/${point?.ma60 ?? "—"}`,
        `DIF ${point?.macd ?? "—"} DEA ${point?.signal ?? "—"} MACD ${point?.histogram ?? "—"}`,
      ].join(" · "));
    };
    currentChart.subscribeCrosshairMove(handler);
    return () => currentChart.unsubscribeCrosshairMove(handler);
  }, [bars, indicators]);

  return <section>
    <div className="realtime-minute-chart" ref={host} role="img"
      onMouseMove={(event) => {
        const text = crosshairTextAt(event.clientX, event.currentTarget, bars, indicators);
        if (text) setCrosshairText(text);
      }}
      aria-label={`${instrumentId} 分钟 K 线、成交量与成交额`} />
    {forming ? <p className="history-coverage-note" data-state="forming">
      形成中 · {frequency} 分钟 · O {forming.open} H {forming.high} L {forming.low} C {forming.close}
      {" · "}量 {forming.volume} 额 {forming.amount}
    </p> : null}
    <p className="history-coverage-note">
      {indicatorState === "insufficient_seed"
        ? "MA / MACD：闭合种子不足（insufficient_seed）"
        : "MA / MACD：闭合种子充足"}
      {" · "}{crosshairText}
    </p>
  </section>;
}

function useChartSeries(host: RefObject<HTMLDivElement | null>) {
  const chart = useRef<IChartApi | null>(null);
  const candle = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const volume = useRef<ISeriesApi<"Histogram"> | null>(null);
  const amount = useRef<ISeriesApi<"Histogram"> | null>(null);
  const maLines = useRef<ISeriesApi<"Line">[]>([]);
  const macd = useRef<ISeriesApi<"Histogram"> | null>(null);
  const dif = useRef<ISeriesApi<"Line"> | null>(null);
  const dea = useRef<ISeriesApi<"Line"> | null>(null);
  useEffect(() => {
    if (!host.current) return;
    chart.current = createChart(host.current, {
      autoSize: true, height: 360,
      layout: {
        background: { type: ColorType.Solid, color: "#fbfcfa" },
        textColor: "#52616a",
      },
      grid: { vertLines: { color: "#edf0ed" }, horzLines: { color: "#edf0ed" } },
      timeScale: { timeVisible: true, secondsVisible: false, borderColor: "#d8dfdb" },
      rightPriceScale: { borderColor: "#d8dfdb" }, crosshair: { mode: 1 },
    });
    candle.current = chart.current.addSeries(CandlestickSeries, {
      upColor: "#b2483f", downColor: "#2f7c68", borderVisible: false,
      wickUpColor: "#b2483f", wickDownColor: "#2f7c68",
    });
    volume.current = chart.current.addSeries(HistogramSeries, {
      priceFormat: { type: "volume" }, priceScaleId: "",
    });
    volume.current.priceScale().applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });
    amount.current = chart.current.addSeries(HistogramSeries, {
      priceFormat: { type: "volume" }, priceScaleId: "amount",
    });
    amount.current.priceScale().applyOptions({ scaleMargins: { top: 0.91, bottom: 0 } });
    maLines.current = ["#7a5ea8", "#1d6b8f", "#a46a1f", "#59636b"].map(
      (color) => chart.current!.addSeries(LineSeries, {
        color, lineWidth: 1, priceLineVisible: false, lastValueVisible: false,
      }),
    );
    macd.current = chart.current.addSeries(HistogramSeries, {
      priceScaleId: "macd", priceLineVisible: false, lastValueVisible: false,
    });
    macd.current.priceScale().applyOptions({ scaleMargins: { top: 0.72, bottom: 0 } });
    dif.current = chart.current.addSeries(LineSeries, {
      color: "#7a5ea8", priceScaleId: "macd", lineWidth: 1,
      priceLineVisible: false, lastValueVisible: false,
    });
    dea.current = chart.current.addSeries(LineSeries, {
      color: "#1d6b8f", priceScaleId: "macd", lineWidth: 1,
      priceLineVisible: false, lastValueVisible: false,
    });
    return () => {
      chart.current?.remove();
      chart.current = null;
      candle.current = null;
      volume.current = null;
      amount.current = null;
      maLines.current = [];
      macd.current = null;
      dif.current = null;
      dea.current = null;
    };
  }, [host]);
  return { chart, candle, volume, amount, maLines, macd, dif, dea };
}

function toTime(value: string): Time {
  return Math.floor(new Date(value).getTime() / 1000) as Time;
}

function crosshairTextAt(
  clientX: number,
  host: HTMLDivElement,
  bars: RealtimeMinuteBar[],
  indicators: RealtimeIndicatorPoint[],
): string | null {
  const drawable = bars.filter((row) => row.is_complete && row.known_gaps.length === 0);
  if (!drawable.length) return null;
  const bounds = host.getBoundingClientRect();
  const ratio = Math.max(0, Math.min(0.999, (clientX - bounds.left) / bounds.width));
  const bar = drawable[Math.floor(ratio * drawable.length)];
  const point = indicators.find((row) => row.minute === bar.minute);
  return [
    `O ${bar.open} H ${bar.high} L ${bar.low} C ${bar.close}`,
    `量 ${bar.volume} 额 ${bar.amount}`,
    `MA ${point?.ma5 ?? "—"}/${point?.ma10 ?? "—"}/${point?.ma30 ?? "—"}/${point?.ma60 ?? "—"}`,
    `DIF ${point?.macd ?? "—"} DEA ${point?.signal ?? "—"} MACD ${point?.histogram ?? "—"}`,
  ].join(" · ");
}
