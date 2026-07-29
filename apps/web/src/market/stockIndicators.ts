import type { Candle } from "./candleFixture";

export type Indicator = "MACD" | "RSI" | "KDJ";
export type MovingAverageWindow = 5 | 10 | 30 | 60 | 120;

export interface IndicatorPoint {
  time: string;
  values: Record<string, number>;
}

export function movingAverage(candles: Candle[], window: number) {
  const result: { time: string; value: number }[] = [];
  let sum = 0;
  for (let index = 0; index < candles.length; index += 1) {
    sum += candles[index].close;
    if (index >= window) sum -= candles[index - window].close;
    if (index + 1 >= window) {
      result.push({ time: candles[index].time, value: sum / window });
    }
  }
  return result;
}

export function macd(candles: Candle[]): IndicatorPoint[] {
  const closes = candles.map((item) => item.close);
  const fast = ema(closes, 12);
  const slow = ema(closes, 26);
  const dif = closes.map((_, index) => fast[index] - slow[index]);
  const dea = ema(dif, 9);
  return candles.map((item, index) => ({
    time: item.time,
    values: {
      DIF: dif[index],
      DEA: dea[index],
      MACD: 2 * (dif[index] - dea[index]),
    },
  }));
}

export function rsi(candles: Candle[], period = 14): IndicatorPoint[] {
  if (candles.length <= period) return [];
  const gains: number[] = [];
  const losses: number[] = [];
  for (let index = 1; index < candles.length; index += 1) {
    const change = candles[index].close - candles[index - 1].close;
    gains.push(Math.max(change, 0));
    losses.push(Math.max(-change, 0));
  }
  let averageGain = average(gains.slice(0, period));
  let averageLoss = average(losses.slice(0, period));
  const result: IndicatorPoint[] = [];
  for (let index = period; index < candles.length; index += 1) {
    if (index > period) {
      averageGain = (averageGain * (period - 1) + gains[index - 1]) / period;
      averageLoss = (averageLoss * (period - 1) + losses[index - 1]) / period;
    }
    const value = averageLoss === 0
      ? 100
      : 100 - 100 / (1 + averageGain / averageLoss);
    result.push({ time: candles[index].time, values: { RSI: value } });
  }
  return result;
}

export function kdj(candles: Candle[], period = 9): IndicatorPoint[] {
  let k = 50;
  let d = 50;
  const result: IndicatorPoint[] = [];
  for (let index = period - 1; index < candles.length; index += 1) {
    const window = candles.slice(index + 1 - period, index + 1);
    const lowest = Math.min(...window.map((item) => item.low));
    const highest = Math.max(...window.map((item) => item.high));
    const rsv = highest === lowest
      ? 50
      : ((candles[index].close - lowest) / (highest - lowest)) * 100;
    k = (2 * k + rsv) / 3;
    d = (2 * d + k) / 3;
    result.push({
      time: candles[index].time,
      values: { K: k, D: d, J: 3 * k - 2 * d },
    });
  }
  return result;
}

export function indicatorValues(candles: Candle[], indicator: Indicator) {
  if (indicator === "MACD") return macd(candles);
  if (indicator === "RSI") return rsi(candles);
  return kdj(candles);
}

export function returnToCutoff(hoveredClose: number, cutoffClose: number) {
  if (hoveredClose <= 0 || cutoffClose <= 0) {
    throw new Error("收盘价必须为正数");
  }
  return cutoffClose / hoveredClose - 1;
}

function ema(values: number[], period: number): number[] {
  if (!values.length) return [];
  const multiplier = 2 / (period + 1);
  const result = [values[0]];
  for (let index = 1; index < values.length; index += 1) {
    result.push(values[index] * multiplier + result[index - 1] * (1 - multiplier));
  }
  return result;
}

function average(values: number[]) {
  return values.reduce((total, value) => total + value, 0) / values.length;
}
