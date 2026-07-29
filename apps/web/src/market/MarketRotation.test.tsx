import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
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
      trade_date: "2026-07-24", relative_trend: 116, relative_momentum: 99,
      quadrant: "lagging", coverage: 1, constituent_count: 8,
      direction_x: 17, direction_y: -2, overflow: true,
    },
  ],
  events: [{
    industry_code: "801010.SI", industry_name: "合成行业甲",
    from_quadrant: "weakening", to_quadrant: "leading",
    first_cross_date: "2026-07-23", confirmed_date: "2026-07-24",
    formula_version: "rotation-index-ew-v1.0.0",
  }],
  created_at: "2026-07-24T18:00:00+08:00",
  content_hash: `sha256:${"3".repeat(64)}`,
  known_gaps: [
    "price_relative_strength_proxy_not_direct_capital_flow",
    "expected_completed_trade_date:2026-07-28",
  ],
};

afterEach(() => {
  vi.restoreAllMocks();
  window.history.replaceState(null, "", "/");
});

test("loads one bounded rotation payload and keeps date, details and URL synchronized", async () => {
  window.history.replaceState(null, "", "/market?trail=20");
  const fetch = vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
    const value = String(input);
    const body = value.includes("industry-hierarchy")
      ? {
          status: "blocked",
          data_snapshot_id: payload.data_snapshot_id,
          as_of: "2026-07-24",
          level: "L2",
          comparison_scope: "siblings",
          benchmark_id: "SW2021:hierarchy:unavailable",
          parent_code: "801010.SI",
          selected_code: null,
          nodes: [],
          rotation: null,
          candles: [],
          known_gaps: ["sw2021_l2_not_published"],
        }
      : payload;
    return Promise.resolve(new Response(JSON.stringify(body), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    }));
  });
  render(<MarketRotation />);

  expect((await screen.findAllByText("研究观察，不是买卖信号")).length).toBeGreaterThan(0);
  expect(screen.getByRole("heading", { name: "2 个行业" })).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: /合成行业甲.*强势领先/ }));
  expect(screen.getByRole("heading", { name: "合成行业甲" })).toBeInTheDocument();
  expect(screen.getByText("102.00")).toBeInTheDocument();
  expect(screen.getByText(/已过期 · 预期 2026-07-28/)).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "查看恢复状态" })).toHaveAttribute(
    "href",
    "/system",
  );
  expect(fetch.mock.calls.filter(([input]) =>
    String(input).includes("/api/market/industry-rotation"))).toHaveLength(1);
  fireEvent.change(screen.getByRole("combobox", { name: "象限筛选" }), {
    target: { value: "leading" },
  });
  fireEvent.change(screen.getByRole("combobox", { name: "排序字段" }), {
    target: { value: "momentum" },
  });
  await waitFor(() => {
    expect(window.location.search).toContain("quadrant=leading");
    expect(window.location.search).toContain("sort=momentum");
  });
  expect(screen.getByRole("button", { name: "展开行业列表" }))
    .toHaveTextContent("1 / 2");
  expect(screen.getByRole("button", { name: /合成行业乙/ })).toHaveClass("is-dimmed");
  expect(fetch.mock.calls.filter(([input]) =>
    String(input).includes("/api/market/industry-rotation"))).toHaveLength(1);
  fireEvent.click(screen.getByRole("button", { name: "重置" }));
  fireEvent.click(screen.getByRole("button", { name: "刷新快照" }));
  await waitFor(() => expect(fetch.mock.calls.filter(([input]) =>
    String(input).includes("/api/market/industry-rotation"))).toHaveLength(2));

  fireEvent.click(screen.getByRole("button", { name: "展开行业列表" }));
  expect(within(screen.getByRole("listbox", {
    name: "申万一级行业",
  })).getAllByRole("option")).toHaveLength(2);
  fireEvent.click(screen.getByRole("button", { name: "全部行业" }));
  expect(screen.getByRole("region", {
    name: "行业相对轮动四象限",
  })).toHaveAttribute("data-trail-count", "2");
  expect(window.location.search).toContain("trail_mode=all");
  expect(screen.getByRole("button", {
    name: /合成行业乙.*坐标已截断/,
  })).toHaveClass("is-edge-right", "has-overflow");

  fireEvent.click(screen.getByRole("button", { name: "清除行业选择" }));
  expect(screen.getByRole("heading", { name: "2 个行业" })).toBeInTheDocument();
  expect(window.location.search).not.toContain("industry=");

  fireEvent.click(screen.getByRole("button", { name: /合成行业甲.*强势领先/ }));
  fireEvent.click(screen.getByRole("button", { name: "进入二级行业" }));
  expect(await screen.findByRole("heading", {
    name: "二级行业数据尚未发布",
  })).toBeInTheDocument();
  expect(screen.getByText(/当前数据快照不包含 SW2021 二级行业分类或指数/))
    .toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "刷新当前快照" }));
  await waitFor(() => expect(fetch.mock.calls.filter(([input]) =>
    String(input).includes("/api/market/industry-hierarchy"))).toHaveLength(2));
  expect(screen.getByText(/不会使用 L1 或当前成员替代/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "一级行业" }));

  fireEvent.click(screen.getByRole("button", { name: "公式与口径" }));
  expect(screen.getByRole("complementary", {
    name: "公式与口径",
  })).toHaveTextContent("价格相对强弱，而非资金净流入");
  expect(screen.getByText(/100 \+ 5 × clip/)).toBeInTheDocument();

  fireEvent.change(screen.getByRole("slider", { name: "轮动日期" }), {
    target: { value: "0" },
  });
  await waitFor(() => expect(window.location.search).toContain("as_of=2026-07-23"));
  expect(fetch.mock.calls.filter(([input]) =>
    String(input).includes("/api/market/industry-rotation"))).toHaveLength(3);
});
