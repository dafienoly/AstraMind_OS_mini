import { describe, expect, it } from "vitest";

import type { RealtimeMinuteBar } from "../types";
import {
  buildRealtimeDisplayBars,
  realtimeMinuteFrequencies,
} from "./realtimeMinuteAggregation";

describe("realtime minute local aggregation", () => {
  it.each(realtimeMinuteFrequencies)("keeps %im forming output at its session anchor", (frequency) => {
    const start = new Date("2026-07-30T09:30:00+08:00");
    const closed = Array.from({ length: 4 }, (_, index) => bar(
      new Date(start.getTime() + index * 60_000).toISOString(), true,
    ));
    const live = bar(new Date(start.getTime() + 4 * 60_000).toISOString(), false);

    const result = buildRealtimeDisplayBars([], closed, [live], frequency);

    expect(result).toHaveLength(1);
    expect(result[0].lifecycle).toBe("forming");
    expect(result[0].minute).toBe(
      frequency === 1 ? new Date(start.getTime() + 4 * 60_000).toISOString()
        : start.toISOString(),
    );
  });

  it("anchors afternoon independently and rejects a missing source minute", () => {
    const start = new Date("2026-07-30T13:00:00+08:00");
    const closed = [0, 1, 3].map((index) => bar(
      new Date(start.getTime() + index * 60_000).toISOString(), true,
    ));
    const live = bar(new Date(start.getTime() + 4 * 60_000).toISOString(), false);

    expect(buildRealtimeDisplayBars([], closed, [live], 5)).toEqual([]);
    expect(buildRealtimeDisplayBars([], [...closed, bar(
      new Date(start.getTime() + 2 * 60_000).toISOString(), true,
    )], [live], 5)[0].minute).toBe(start.toISOString());
  });

  it("never mixes a raw 1m row into a non-1m series", () => {
    const live = bar("2026-07-30T10:07:00+08:00", false);
    const highPeriod = bar("2026-07-30T09:45:00+08:00", true);

    const result = buildRealtimeDisplayBars([highPeriod], [], [live], 15);

    expect(result).toEqual([highPeriod]);
  });
});

function bar(minute: string, complete: boolean): RealtimeMinuteBar {
  return {
    provider: "miniqmt", session_id: `sha256:${"1".repeat(64)}`,
    instrument_id: "000001.SZ", minute,
    open: 10, high: 11, low: 9, close: 10.5, volume: 1, amount: 10,
    observation_count: 1, source_kind: "l1",
    source_identity: `sha256:${"2".repeat(64)}`,
    is_complete: complete, known_gaps: [],
    lifecycle: complete ? "sealed" : "forming",
  };
}
