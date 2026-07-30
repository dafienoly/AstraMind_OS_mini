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
import { useEffect, useRef } from "react";

import type { RealtimeIndicatorPoint, RealtimeMinuteBar } from "../types";

export function RealtimeMinuteChart({
  instrumentId,
  bars,
  indicatorState = "ready",
  indicators = [],
}: {
  instrumentId: string;
  bars: RealtimeMinuteBar[];
  indicatorState?: "ready" | "insufficient_seed";
  indicators?: RealtimeIndicatorPoint[];
}) {
  const host = useRef<HTMLDivElement>(null);
  const chart = useRef<IChartApi | null>(null);
  const candle = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const volume = useRef<ISeriesApi<"Histogram"> | null>(null);
  const amount = useRef<ISeriesApi<"Histogram"> | null>(null);
  const maLines = useRef<ISeriesApi<"Line">[]>([]);
  const macd = useRef<ISeriesApi<"Histogram"> | null>(null);

  useEffect(() => {
    if (!host.current) return;
    chart.current = createChart(host.current, {
      autoSize: true,
      height: 360,
      layout: {
        background: { type: ColorType.Solid, color: "#fbfcfa" },
        textColor: "#52616a",
      },
      grid: {
        vertLines: { color: "#edf0ed" },
        horzLines: { color: "#edf0ed" },
      },
      timeScale: { timeVisible: true, secondsVisible: false, borderColor: "#d8dfdb" },
      rightPriceScale: { borderColor: "#d8dfdb" },
      crosshair: { mode: 1 },
    });
    candle.current = chart.current.addSeries(CandlestickSeries, {
      upColor: "#b2483f",
      downColor: "#2f7c68",
      borderVisible: false,
      wickUpColor: "#b2483f",
      wickDownColor: "#2f7c68",
    });
    volume.current = chart.current.addSeries(HistogramSeries, {
      priceFormat: { type: "volume" },
      priceScaleId: "",
    });
    volume.current.priceScale().applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });
    amount.current = chart.current.addSeries(HistogramSeries, {
      priceFormat: { type: "volume" },
      priceScaleId: "amount",
    });
    amount.current.priceScale().applyOptions({ scaleMargins: { top: 0.91, bottom: 0 } });
    maLines.current = ["#7a5ea8", "#1d6b8f", "#a46a1f", "#59636b"].map(
      (color) => chart.current!.addSeries(LineSeries, {
        color,
        lineWidth: 1,
        priceLineVisible: false,
        lastValueVisible: false,
      }),
    );
    macd.current = chart.current.addSeries(HistogramSeries, {
      priceScaleId: "macd",
      priceLineVisible: false,
      lastValueVisible: false,
    });
    macd.current.priceScale().applyOptions({ scaleMargins: { top: 0.72, bottom: 0 } });
    return () => {
      chart.current?.remove();
      chart.current = null;
      candle.current = null;
      volume.current = null;
      amount.current = null;
      maLines.current = [];
      macd.current = null;
    };
  }, []);

  useEffect(() => {
    if (!candle.current || !volume.current || !amount.current) return;
    const values = bars.map((row) => ({
      time: toTime(row.minute),
      open: row.open,
      high: row.high,
      low: row.low,
      close: row.close,
    }));
    const volumes = bars.map((row) => ({
      time: toTime(row.minute),
      value: row.volume,
      color: row.close >= row.open ? "#b2483f66" : "#2f7c6866",
    }));
    const amounts = bars.map((row) => ({
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
  }, [indicators]);

  return <section>
    <div className="realtime-minute-chart" ref={host} role="img"
      aria-label={`${instrumentId} 分钟 K 线、成交量与成交额`} />
    <p className="history-coverage-note">
      {indicatorState === "insufficient_seed"
        ? "MA / MACD：闭合种子不足（insufficient_seed）"
        : "MA / MACD：闭合种子充足"}
      {" · "}成交额随十字光标对应分钟读取
    </p>
  </section>;
}

function toTime(value: string): Time {
  return Math.floor(new Date(value).getTime() / 1000) as Time;
}
