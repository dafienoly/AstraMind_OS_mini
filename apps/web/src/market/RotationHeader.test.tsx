import { render, screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";

import { RotationHeader } from "./RotationPanels";
import type { RotationSnapshot } from "./rotationTypes";

const snapshot: RotationSnapshot = {
  rotation_snapshot_id: "rotation-test",
  data_snapshot_id: "data-test",
  as_of: "2026-07-28T15:30:00+08:00",
  benchmark_id: "SW2021:L1:equal-weight",
  benchmark_definition_version: "v1",
  formula: {
    formula_version: "rotation-index-ew-v1.0.0",
    fast_window: 20,
    slow_window: 60,
    momentum_window: 5,
    warmup_sessions: 80,
    output_sessions: 60,
    scale: 5,
    clip_z: 3,
    neutral_band: 0.25,
    confirmation_sessions: 2,
    required_industry_coverage: 1,
    minimum_constituent_count: 5,
    rounding_decimals: 8,
  },
  taxonomy: "SW",
  taxonomy_version: "SW2021",
  industry_count: 31,
  covered_industry_count: 31,
  coverage_rule: "complete",
  date_range: ["2026-07-28", "2026-07-28"],
  dates: ["2026-07-28"],
  points: [],
  events: [],
  created_at: "2026-07-28T18:00:00+08:00",
  content_hash: `sha256:${"0".repeat(64)}`,
  known_gaps: [],
};

test("renders only the rotation status because first-level navigation belongs to AppShell", () => {
  render(
    <RotationHeader
      onRefresh={vi.fn()}
      refreshing={false}
      snapshot={snapshot}
    />,
  );

  expect(screen.queryByRole("navigation", { name: "一级导航" })).not.toBeInTheDocument();
  expect(screen.getByText(/2026-07-28 快照内完整/)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "刷新快照" })).toBeInTheDocument();
});
