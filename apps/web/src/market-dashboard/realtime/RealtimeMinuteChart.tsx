import {
  CandlestickSeries,
  ColorType,
  createChart,
  HistogramSeries,
  type IChartApi,
  type ISeriesApi,
  type Time,
} from "lightweight-charts";
import { useEffect, useRef } from "react";

import type { RealtimeMinuteBar } from "../types";

export function RealtimeMinuteChart({
  instrumentId,
  bars,
}: {
  instrumentId: string;
  bars: RealtimeMinuteBar[];
}) {
  const host = useRef<HTMLDivElement>(null);
  const chart = useRef<IChartApi | null>(null);
  const candle = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const volume = useRef<ISeriesApi<"Histogram"> | null>(null);
  const loadedInstrument = useRef("");
  const loadedCount = useRef(0);

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
    return () => {
      chart.current?.remove();
      chart.current = null;
      candle.current = null;
      volume.current = null;
    };
  }, []);

  useEffect(() => {
    if (!candle.current || !volume.current) return;
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
    if (loadedInstrument.current !== instrumentId || loadedCount.current === 0) {
      candle.current.setData(values);
      volume.current.setData(volumes);
      chart.current?.timeScale().fitContent();
    } else if (values.length >= loadedCount.current && values.length) {
      candle.current.update(values.at(-1)!);
      volume.current.update(volumes.at(-1)!);
    } else {
      candle.current.setData(values);
      volume.current.setData(volumes);
    }
    loadedInstrument.current = instrumentId;
    loadedCount.current = values.length;
  }, [bars, instrumentId]);

  return <div className="realtime-minute-chart" ref={host} role="img"
    aria-label={`${instrumentId} 一分钟 K 线`} />;
}

function toTime(value: string): Time {
  return Math.floor(new Date(value).getTime() / 1000) as Time;
}
