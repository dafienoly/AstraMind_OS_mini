import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import { MarketRotation } from "./MarketRotation";

const payload = {
  rotation_snapshot_id: `rotation:sha256:${"1".repeat(64)}`,
  data_snapshot_id: `snapshot:sha256:${"2".repeat(64)}`,
  as_of: "2026-07-24T18:00:00+08:00",
  benchmark_id: "SW2021:L1:equal_weight_index_return",
  benchmark_definition_version: "1.0.0",
  formula: {
    formula_version: "rotation-index-ew-v1.0.0",
    fast_window: 20,
    slow_window: 60,
    momentum_window: 5,
    neutral_band: 0.25,
    confirmation_sessions: 2,
  },
  taxonomy_version: "SW2021",
  industry_count: 2,
  covered_industry_count: 2,
  coverage_rule: "synthetic test coverage",
  date_range: ["2026-07-23", "2026-07-24"],
  dates: ["2026-07-23", "2026-07-24"],
  points: [
    {
      industry_code: "801010.SI", industry_name: "合成行业甲",
      trade_date: "2026-07-23", relative_trend: 101, relative_momentum: 99,
      quadrant: "weakening", coverage: 1, constituent_count: 10,
      direction_x: 0, direction_y: 0, overflow: false,
    },
    {
      industry_code: "801010.SI", industry_name: "合成行业甲",
      trade_date: "2026-07-24", relative_trend: 102, relative_momentum: 101,
      quadrant: "leading", coverage: 1, constituent_count: 10,
      direction_x: 1, direction_y: 2, overflow: false,
    },
    {
      industry_code: "801020.SI", industry_name: "合成行业乙",
      trade_date: "2026-07-23", relative_trend: 99, relative_momentum: 101,
      quadrant: "improving", coverage: 1, constituent_count: 8,
      direction_x: 0, direction_y: 0, overflow: false,
    },
    {
      industry_code: "801020.SI", industry_name: "合成行业乙",
      trade_date: "2026-07-24", relative_trend: 98, relative_momentum: 99,
      quadrant: "lagging", coverage: 1, constituent_count: 8,
      direction_x: -1, direction_y: -2, overflow: false,
    },
  ],
  events: [{
    industry_code: "801010.SI", industry_name: "合成行业甲",
    from_quadrant: "weakening", to_quadrant: "leading",
    first_cross_date: "2026-07-23", confirmed_date: "2026-07-24",
    formula_version: "rotation-index-ew-v1.0.0",
  }],
  content_hash: `sha256:${"3".repeat(64)}`,
  known_gaps: ["price_relative_strength_proxy_not_direct_capital_flow"],
};

afterEach(() => {
  vi.restoreAllMocks();
  window.history.replaceState(null, "", "/");
});

test("loads one bounded rotation payload and keeps date, details and URL synchronized", async () => {
  window.history.replaceState(null, "", "/market?trail=20");
  const fetch = vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(JSON.stringify(payload), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    }),
  );
  render(<MarketRotation />);

  expect((await screen.findAllByText("研究观察，不是买卖信号")).length).toBeGreaterThan(0);
  expect(screen.getByRole("heading", { name: "合成行业甲" })).toBeInTheDocument();
  expect(screen.getByText("102.00")).toBeInTheDocument();
  expect(fetch).toHaveBeenCalledTimes(1);

  fireEvent.change(screen.getByRole("slider", { name: "轮动日期" }), {
    target: { value: "0" },
  });
  await waitFor(() => expect(window.location.search).toContain("as_of=2026-07-23"));
  expect(fetch).toHaveBeenCalledTimes(1);
});
