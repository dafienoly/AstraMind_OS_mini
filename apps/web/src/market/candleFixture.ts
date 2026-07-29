export type Candle = {
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  amount?: number | null;
};

export type Timeframe = "日线" | "周线" | "月线";

export const decisionCutoff = "2025-05-31";

export function buildCandleFixture(): Candle[] {
  const start = Date.UTC(2025, 0, 2);
  const rows: Candle[] = [];
  let close = 36.4;
  for (let offset = 0; rows.length < 112; offset += 1) {
    const current = new Date(start + offset * 86_400_000);
    if (current.getUTCDay() === 0 || current.getUTCDay() === 6) continue;
    const pulse = Math.sin(rows.length / 5) * 0.52 + Math.cos(rows.length / 13) * 0.28;
    const open = close + Math.sin(rows.length * 1.7) * 0.19;
    close = Math.max(28, open + pulse * 0.38);
    rows.push({
      time: current.toISOString().slice(0, 10),
      open: round(open),
      high: round(Math.max(open, close) + 0.24 + Math.abs(pulse) * 0.12),
      low: round(Math.min(open, close) - 0.22 - Math.abs(pulse) * 0.1),
      close: round(close),
      volume: Math.round(4_800_000 + (1 + pulse) * 1_400_000 + rows.length * 8_000),
    });
  }
  return rows;
}

export function visibleAt(candles: Candle[], cutoff: string): Candle[] {
  return candles.filter((candle) => candle.time <= cutoff);
}

export function aggregateCandles(candles: Candle[], timeframe: Timeframe): Candle[] {
  if (timeframe === "日线") return candles;
  const groups = new Map<string, Candle[]>();
  for (const candle of candles) {
    const key = timeframe === "月线" ? candle.time.slice(0, 7) : weekKey(candle.time);
    groups.set(key, [...(groups.get(key) ?? []), candle]);
  }
  return [...groups.values()].map((group) => ({
    time: group.at(-1)?.time ?? "",
    open: group[0].open,
    high: Math.max(...group.map((item) => item.high)),
    low: Math.min(...group.map((item) => item.low)),
    close: group.at(-1)?.close ?? group[0].close,
    volume: group.reduce((total, item) => total + item.volume, 0),
    amount: group.some((item) => item.amount != null)
      ? group.reduce((total, item) => total + (item.amount ?? 0), 0)
      : null,
  }));
}

function weekKey(value: string): string {
  const current = new Date(`${value}T00:00:00Z`);
  const day = current.getUTCDay() || 7;
  current.setUTCDate(current.getUTCDate() - day + 1);
  return current.toISOString().slice(0, 10);
}

function round(value: number): number {
  return Math.round(value * 100) / 100;
}
