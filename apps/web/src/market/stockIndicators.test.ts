import { expect, test } from "vitest";

import type { Candle } from "./candleFixture";
import { indicatorValues, movingAverage, returnToCutoff } from "./stockIndicators";

const candles: Candle[] = Array.from({ length: 140 }, (_, index) => ({
  time: `2026-${String(Math.floor(index / 28) + 1).padStart(2, "0")}-${String(index % 28 + 1).padStart(2, "0")}`,
  open: 10 + index,
  high: 11 + index,
  low: 9 + index,
  close: 10 + index,
  volume: 1000 + index,
}));

test("moving averages require the exact selected-period window", () => {
  expect(movingAverage(candles, 5)).toHaveLength(136);
  expect(movingAverage(candles, 120)).toHaveLength(21);
  expect(movingAverage(candles.slice(0, 119), 120)).toEqual([]);
});

test("hover return uses the selected-period close and immutable cutoff close", () => {
  expect(returnToCutoff(80, 100)).toBeCloseTo(0.25);
  expect(() => returnToCutoff(0, 100)).toThrow("收盘价必须为正数");
});

test("MACD RSI and KDJ produce finite aligned values", () => {
  for (const indicator of ["MACD", "RSI", "KDJ"] as const) {
    const values = indicatorValues(candles, indicator);
    expect(values.length).toBeGreaterThan(0);
    expect(values.every((point) =>
      Object.values(point.values).every(Number.isFinite))).toBe(true);
    expect(values.at(-1)?.time).toBe(candles.at(-1)?.time);
  }
});
