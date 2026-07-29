import { describe, expect, test } from "vitest";

import { motionMetrics } from "./rotationIdentity";
import {
  buildRotationScreenRows,
  type RotationScreenOptions,
} from "./rotationScreening";
import type { RotationPoint } from "./rotationTypes";

const base: RotationPoint = {
  industry_code: "A",
  industry_name: "甲",
  trade_date: "2026-07-28",
  relative_trend: 101,
  relative_momentum: 101,
  quadrant: "leading",
  coverage: 1,
  constituent_count: 3,
  direction_x: 0,
  direction_y: 0,
  overflow: false,
};

const defaults: RotationScreenOptions = {
  search: "",
  quadrant: "",
  motion: "",
  sort: "name",
  order: "asc",
};

function history(momentums: number[], code = "A", name = "甲") {
  return momentums.map((relative_momentum, index) => ({
    ...base,
    industry_code: code,
    industry_name: name,
    trade_date: `2026-07-${26 + index}`,
    relative_momentum,
  }));
}

describe("rotation motion v2", () => {
  test.each([
    [[100, 101, 103], "accelerating_up"],
    [[100, 103, 104], "decelerating_up"],
    [[100, 99, 97], "accelerating_down"],
    [[100, 97, 96], "decelerating_down"],
  ] as const)("classifies %j as %s", (values, expected) => {
    expect(motionMetrics(history([...values])).state).toBe(expected);
  });

  test("keeps insufficient and epsilon-sized movement steady", () => {
    expect(motionMetrics(history([100, 101])).state).toBe("steady");
    expect(motionMetrics(history([100, 101, 101.01])).state).toBe("steady");
  });
});

describe("rotation screening", () => {
  const identities = [
    { code: "B", name: "乙" },
    { code: "A", name: "甲" },
    { code: "C", name: "丙" },
  ];
  const points = [
    ...history([100, 101, 103], "A", "甲"),
    ...history([100, 99, 97], "B", "乙").map((point) => ({
      ...point,
      relative_trend: 99,
      quadrant: "lagging" as const,
    })),
  ];
  const current = points.filter((point) => point.trade_date === "2026-07-28");

  test("combines name, quadrant, and motion filters", () => {
    const rows = buildRotationScreenRows({
      identities,
      current,
      history: points,
      options: {
        ...defaults,
        search: "A",
        quadrant: "leading",
        motion: "accelerating_up",
      },
    });
    expect(rows.map((row) => row.code)).toEqual(["A"]);
  });

  test("sorts metrics stably and always places unavailable values last", () => {
    const descending = buildRotationScreenRows({
      identities,
      current,
      history: points,
      options: { ...defaults, sort: "speed", order: "desc" },
    });
    expect(descending.map((row) => row.code)).toEqual(["A", "B", "C"]);
    const ascending = buildRotationScreenRows({
      identities,
      current,
      history: points,
      options: { ...defaults, sort: "speed", order: "asc" },
    });
    expect(ascending.map((row) => row.code)).toEqual(["A", "B", "C"]);
  });

  test("uses code ascending to break exact numeric ties", () => {
    const rows = buildRotationScreenRows({
      identities: identities.slice(0, 2),
      current,
      history: points,
      options: { ...defaults, sort: "speed", order: "desc" },
    });
    expect(rows.map((row) => row.code)).toEqual(["A", "B"]);
  });
});
