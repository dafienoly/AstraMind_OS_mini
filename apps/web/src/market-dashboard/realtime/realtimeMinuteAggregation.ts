import type { RealtimeMinuteBar } from "../types";

export function buildRealtimeDisplayBars(
  history: RealtimeMinuteBar[],
  todayClosedOneMinute: RealtimeMinuteBar[],
  liveOneMinute: RealtimeMinuteBar[],
  frequency: number,
): RealtimeMinuteBar[] {
  const safeLive = liveOneMinute.filter((row) => (
    row.lifecycle === "forming" && !row.is_complete && row.known_gaps.length === 0
  ));
  if (frequency === 1) return mergeByMinute(history, safeLive);
  const forming = aggregateCurrentBucket(todayClosedOneMinute, safeLive, frequency);
  return mergeByMinute(history, forming ? [forming] : []);
}

function aggregateCurrentBucket(
  closed: RealtimeMinuteBar[],
  live: RealtimeMinuteBar[],
  frequency: number,
): RealtimeMinuteBar | null {
  const current = live.at(-1);
  if (!current) return null;
  const anchor = bucketAnchor(current.minute, frequency);
  if (!anchor) return null;
  const candidates = [...closed, current]
    .filter((row) => row.instrument_id === current.instrument_id)
    .filter((row) => {
      const minute = new Date(row.minute).getTime();
      return minute >= anchor.getTime() && minute <= new Date(current.minute).getTime();
    })
    .sort((left, right) => left.minute.localeCompare(right.minute));
  const expected = Math.floor(
    (new Date(current.minute).getTime() - anchor.getTime()) / 60_000,
  ) + 1;
  if (candidates.length !== expected || candidates.some((row) => row.known_gaps.length)) {
    return null;
  }
  return {
    ...current,
    minute: anchor.toISOString(),
    open: candidates[0].open,
    high: Math.max(...candidates.map((row) => row.high)),
    low: Math.min(...candidates.map((row) => row.low)),
    close: current.close,
    volume: candidates.reduce((total, row) => total + row.volume, 0),
    amount: candidates.reduce((total, row) => total + row.amount, 0),
    observation_count: candidates.reduce((total, row) => total + row.observation_count, 0),
    source_kind: "reconciled",
    is_complete: false,
    lifecycle: "forming",
    known_gaps: [],
  };
}

function bucketAnchor(value: string, frequency: number): Date | null {
  const epoch = new Date(value).getTime();
  const local = new Date(epoch + 8 * 60 * 60_000);
  const hour = local.getUTCHours();
  const minute = local.getUTCMinutes();
  const sessionStart = hour < 12 ? 9 * 60 + 30 : hour >= 13 ? 13 * 60 : null;
  if (sessionStart == null) return null;
  const offset = hour * 60 + minute - sessionStart;
  if (offset < 0 || offset >= 120) return null;
  const anchorMinute = sessionStart + Math.floor(offset / frequency) * frequency;
  return new Date(Date.UTC(
    local.getUTCFullYear(), local.getUTCMonth(), local.getUTCDate(),
    Math.floor(anchorMinute / 60), anchorMinute % 60,
  ) - 8 * 60 * 60_000);
}

function mergeByMinute(
  history: RealtimeMinuteBar[],
  current: RealtimeMinuteBar[],
): RealtimeMinuteBar[] {
  const values = new Map(history.map((row) => [row.minute, row]));
  for (const row of current) values.set(row.minute, row);
  return [...values.values()].sort((left, right) => left.minute.localeCompare(right.minute));
}

export const realtimeMinuteFrequencies = [1, 5, 15, 30, 60, 120] as const;
