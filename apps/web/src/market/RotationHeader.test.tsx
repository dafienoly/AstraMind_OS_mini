import { render, screen, within } from "@testing-library/react";
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

test("links implemented destinations and marks the unavailable strategy arena", () => {
  render(
    <RotationHeader
      onRefresh={vi.fn()}
      refreshing={false}
      snapshot={snapshot}
    />,
  );

  const navigation = screen.getByRole("navigation", { name: "一级导航" });
  expect(within(navigation).getByRole("link", { name: "今日" }))
    .toHaveAttribute("href", "/today");
  expect(within(navigation).getByText("市场"))
    .toHaveAttribute("aria-current", "page");
  expect(within(navigation).getByLabelText("策略竞技场（尚未开放）"))
    .toHaveAttribute("title", "策略竞技场尚未开放");
  expect(within(navigation).queryByRole("link", { name: /策略竞技场/ }))
    .not.toBeInTheDocument();
  expect(within(navigation).getByRole("link", { name: "组合" }))
    .toHaveAttribute("href", "/portfolio");
  expect(within(navigation).getByRole("link", { name: "系统" }))
    .toHaveAttribute("href", "/system");
});
