import { expect, test } from "vitest";

import {
  continuousPlaybackFrame,
  interpolateRotationPoints,
} from "./rotationPlayback";
import { assessRotationFreshness } from "./rotationFreshness";
import { displayValue, projectVisualPoint, visualPointFromContract } from "./rotationProjection";
import { industryColor, motionState } from "./rotationIdentity";
import type { RotationPoint, RotationSnapshot } from "./rotationTypes";

const point: RotationPoint = {
  industry_code: "801010.SI",
  industry_name: "合成行业",
  trade_date: "2026-07-27",
  relative_trend: 90,
  relative_momentum: 100,
  quadrant: "improving",
  coverage: 1,
  constituent_count: 10,
  direction_x: 0,
  direction_y: 0,
  overflow: false,
};

test("interpolates only visual coordinates and preserves the logical date", () => {
  const next = {
    ...point,
    trade_date: "2026-07-28",
    relative_trend: 110,
    relative_momentum: 120,
    quadrant: "leading" as const,
  };
  const [halfway] = interpolateRotationPoints([point], [next], 0.5);
  expect(halfway.display_trend).toBe(100);
  expect(halfway.display_momentum).toBe(110);
  expect(halfway.trade_date).toBe("2026-07-27");
  expect(halfway.quadrant).toBe("improving");
});

test("freshness is based on an explicit completed-trade-date marker", () => {
  const snapshot = {
    date_range: ["2026-07-01", "2026-07-27"],
    known_gaps: ["expected_completed_trade_date:2026-07-28"],
  } as RotationSnapshot;
  expect(assessRotationFreshness(snapshot)).toEqual({
    kind: "stale",
    latestDate: "2026-07-27",
    expectedDate: "2026-07-28",
  });
});

test("uses the versioned tanh display mapping without changing logical coordinates", () => {
  const transformed = visualPointFromContract({
    ...point,
    raw_z_trend: 9,
    raw_z_momentum: -9,
    display_transform_version: "rotation-display-tanh-v1.0.0",
  });
  expect(transformed.relative_trend).toBe(90);
  expect(transformed.display_trend).toBeCloseTo(displayValue(9));
  expect(transformed.display_trend).toBeGreaterThan(113);
  expect(transformed.display_trend).toBeLessThan(114);
  const projected = projectVisualPoint(transformed);
  expect(projected.x).toBeLessThanOrEqual(95);
  expect(projected.y).toBeGreaterThanOrEqual(8);
});

test("industry identity and directional speed labels are deterministic", () => {
  expect(industryColor("801010.SI")).toBe(industryColor("801010.SI"));
  const history = [99, 101, 102].map((momentum, index) => ({
    ...point,
    trade_date: `2026-07-${25 + index}`,
    relative_momentum: momentum,
  }));
  expect(motionState(history)).toBe("decelerating_up");
});

test("continuous playhead crosses day boundaries without resetting", () => {
  expect(continuousPlaybackFrame(4_900, 10, 0, 4)).toEqual({
    dateIndex: 1,
    withinDay: 0.96,
    done: false,
  });
  const afterBoundary = continuousPlaybackFrame(5_100, 10, 0, 4);
  expect(afterBoundary.dateIndex).toBe(2);
  expect(afterBoundary.withinDay).toBeCloseTo(0.04);
  expect(afterBoundary.done).toBe(false);
  expect(continuousPlaybackFrame(10_000, 10, 0, 4)).toEqual({
    dateIndex: 4,
    withinDay: 0,
    done: true,
  });
});
