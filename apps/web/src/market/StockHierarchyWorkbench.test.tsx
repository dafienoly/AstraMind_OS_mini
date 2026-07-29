import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import { clearHierarchyRequests } from "./hierarchyClient";
import { IndustryHierarchyExplorer } from "./IndustryHierarchyExplorer";
import type { IndustryHierarchyView, RotationSnapshot } from "./rotationTypes";
import { StockHierarchyWorkbench } from "./StockHierarchyWorkbench";

const dates = ["2026-07-26", "2026-07-27"];
const rotation: RotationSnapshot = {
  rotation_snapshot_id: `rotation:sha256:${"1".repeat(64)}`,
  data_snapshot_id: `snapshot:sha256:${"2".repeat(64)}`,
  as_of: "2026-07-27T18:00:00+08:00",
  benchmark_id: "SW2021:L2:801081.SI:member_equal_weight_return",
  benchmark_definition_version: "1.0.0",
  formula: {
    formula_version: "test",
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
    minimum_constituent_count: 1,
    rounding_decimals: 6,
  },
  taxonomy: "SW",
  taxonomy_version: "SW2021",
  industry_count: 2,
  covered_industry_count: 2,
  coverage_rule: "test",
  date_range: [dates[0], dates[1]],
  dates,
  points: ["688981.SH", "688347.SH"].flatMap((code, codeIndex) =>
    dates.map((day, dayIndex) => ({
      industry_code: code,
      industry_name: codeIndex ? "华虹公司" : "中芯国际",
      trade_date: day,
      relative_trend: 101 + codeIndex + dayIndex,
      relative_momentum: 101 + dayIndex,
      quadrant: "leading" as const,
      coverage: 1,
      constituent_count: 1,
      direction_x: 1,
      direction_y: 1,
      overflow: false,
    }))),
  events: [],
  created_at: "2026-07-27T18:00:00+08:00",
  content_hash: `sha256:${"3".repeat(64)}`,
  known_gaps: [],
};
const candles = Array.from({ length: 140 }, (_, index) => ({
  trade_date: `2026-07-${String(index % 28 + 1).padStart(2, "0")}`,
  open: 10 + index,
  high: 11 + index,
  low: 9 + index,
  close: 10.5 + index,
  volume_lots: 1000 + index,
  amount_cny: 2_000_000 + index,
}));
const view: IndustryHierarchyView = {
  status: "ready",
  data_snapshot_id: rotation.data_snapshot_id,
  as_of: "2026-07-27",
  level: "stock",
  comparison_scope: "members",
  benchmark_id: rotation.benchmark_id,
  parent_code: "801080.SI",
  selected_code: "688981.SH",
  nodes: [
    { code: "688981.SH", name: "中芯国际", level: "stock", parent_code: "801081.SI" },
    { code: "688347.SH", name: "华虹公司", level: "stock", parent_code: "801081.SI" },
  ],
  rotation,
  candles,
  weekly_candles: candles.slice(-130),
  monthly_candles: candles.slice(-120),
  stock_evidence: {
    instrument_id: "688981.SH",
    instrument_name: "中芯国际",
    as_of: "2026-07-27",
    fundamental: {
      market_date: "2026-07-27",
      available_at: "2026-07-27T18:00:00+08:00",
      latest_close: 143.77,
      percent_change: 0.0278,
      turnover_rate: 0.0268,
      price_earnings_ttm: 243.93,
      price_book: 8.22,
      total_market_value_cny: 1_230_000_000_000,
      circulating_market_value_cny: 287_000_000_000,
      amount_cny: 7_550_000_000,
    },
    shareholder_concentration: {
      status: "unavailable",
      announced_on: null,
      reporting_period: null,
      available_at: null,
      holder_count: null,
      previous_holder_count: null,
      change_rate: null,
      direction: null,
      consecutive_periods: 0,
      observation_age_days: null,
      known_gaps: ["shareholder_count_not_in_snapshot"],
    },
    known_gaps: ["shareholder_count_not_in_snapshot"],
  },
  known_gaps: [],
};

afterEach(() => {
  cleanup();
  clearHierarchyRequests();
  vi.restoreAllMocks();
  window.history.replaceState(null, "", "/");
});

test("stock quadrant stays interactive and opens the same-snapshot common workbench", () => {
  const onInstrument = vi.fn();
  render(<StockHierarchyWorkbench onInstrument={onInstrument} view={view} />);

  expect(screen.getByRole("region", { name: "个股相对轮动四象限" })).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: /华虹公司.*强势领先/ }));
  expect(onInstrument).toHaveBeenCalledWith("688347.SH");
  const link = screen.getByRole("link", { name: /打开通用个股工作面/ });
  expect(link).toHaveAttribute("href", expect.stringContaining("/stocks/688981.SH"));
  expect(link).toHaveAttribute("href", expect.stringContaining("data_snapshot_id="));
});

test("stock screening dims the plot, sorts the list, and stays client-side", async () => {
  const fetch = vi.spyOn(globalThis, "fetch");
  render(<StockHierarchyWorkbench onInstrument={vi.fn()} view={view} />);

  fireEvent.change(screen.getByRole("combobox", { name: "个股象限筛选" }), {
    target: { value: "lagging" },
  });
  fireEvent.change(screen.getByRole("combobox", { name: "个股排序字段" }), {
    target: { value: "speed" },
  });
  await waitFor(() => {
    expect(window.location.search).toContain("stock_quadrant=lagging");
    expect(window.location.search).toContain("stock_sort=speed");
  });
  expect(document.querySelectorAll(".stock-navigator .rotation-node.is-dimmed"))
    .toHaveLength(2);
  expect(screen.getByText("当前选择不在筛选结果中，股票证据仍保留。"))
    .toBeInTheDocument();
  expect(screen.getByText("没有符合当前条件的对象")).toBeInTheDocument();
  expect(fetch).not.toHaveBeenCalled();

  fireEvent.click(screen.getByRole("button", { name: "重置筛选" }));
  expect(screen.getAllByText(/速度 — · 平稳/)).toHaveLength(2);
});

test("stock rotation focus expands locally and keeps the common-workbench entry mounted", () => {
  const onInstrument = vi.fn();
  const fetch = vi.spyOn(globalThis, "fetch");
  render(<StockHierarchyWorkbench onInstrument={onInstrument} view={view} />);

  const plot = screen.getByRole("region", { name: "个股相对轮动四象限" });
  const entry = document.querySelector(".stock-workbench-entry");
  fireEvent.click(screen.getByRole("button", { name: "展开聚焦" }));

  expect(screen.getByRole("button", { name: "收起" })).toBeInTheDocument();
  expect(screen.getByRole("region", { name: "个股相对轮动四象限" })).toBe(plot);
  expect(document.querySelector(".stock-workbench-entry")).toBe(entry);
  expect(plot).toHaveAttribute("data-trail-count", "1");
  expect(plot).toHaveAttribute("data-label-count", "2");
  expect(plot).toHaveTextContent("华虹公司");

  fireEvent.click(screen.getByRole("button", { name: "放大象限图" }));
  expect(plot).toHaveAttribute("data-zoom", "1.35");
  expect(screen.getByText("名称 · 全部常驻")).toBeVisible();

  const navigation = screen.getByLabelText("个股轮动聚焦导航");
  fireEvent.keyDown(navigation, { key: "ArrowDown" });
  fireEvent.keyDown(navigation, { key: "Enter" });
  expect(onInstrument).toHaveBeenCalledWith("688347.SH");

  fireEvent.keyDown(navigation, { key: "Escape" });
  expect(screen.queryByRole("button", { name: "收起" })).not.toBeInTheDocument();
  expect(screen.getByRole("region", { name: "个股相对轮动四象限" })).toBe(plot);
  expect(document.querySelector(".stock-workbench-entry")).toBe(entry);
  expect(fetch).not.toHaveBeenCalled();
});

test("stock selection keeps navigation mounted and refreshes evidence locally", async () => {
  window.history.replaceState(
    null,
    "",
    "/market?l2=801081.SI&stock=688981.SH",
  );
  let resolveSelection: ((response: Response) => void) | undefined;
  const selection = new Promise<Response>((resolve) => {
    resolveSelection = resolve;
  });
  let requestCount = 0;
  vi.spyOn(globalThis, "fetch").mockImplementation(() => {
    requestCount += 1;
    return requestCount === 1
      ? Promise.resolve(jsonResponse(view))
      : selection;
  });
  render(<IndustryHierarchyExplorer
    asOf="2026-07-27"
    onBack={vi.fn()}
    onRefresh={vi.fn()}
    parentCode="801080.SI"
    parentName="电子"
    refreshing={false}
    snapshot={rotation}
  />);

  expect(await screen.findByRole("heading", { name: "中芯国际" })).toBeInTheDocument();
  const plot = screen.getByRole("region", { name: "个股相对轮动四象限" });
  const entry = document.querySelector(".stock-workbench-entry");
  fireEvent.click(screen.getByRole("button", { name: /华虹公司.*强势领先/ }));

  expect(screen.getByRole("status")).toHaveTextContent("正在切换至 华虹公司");
  expect(screen.queryByRole("heading", { name: "正在读取同一快照" })).not.toBeInTheDocument();
  expect(screen.getByRole("region", { name: "个股相对轮动四象限" })).toBe(plot);
  expect(document.querySelector(".stock-workbench-entry")).toBe(entry);

  const nextView: IndustryHierarchyView = {
    ...view,
    selected_code: "688347.SH",
    stock_evidence: view.stock_evidence ? {
      ...view.stock_evidence,
      instrument_id: "688347.SH",
      instrument_name: "华虹公司",
    } : null,
  };
  await act(async () => {
    resolveSelection?.(jsonResponse(nextView));
    await selection;
  });

  expect(await screen.findByRole("heading", { name: "华虹公司" })).toBeInTheDocument();
  expect(screen.queryByRole("status")).not.toBeInTheDocument();
  expect(screen.getByRole("region", { name: "个股相对轮动四象限" })).toBe(plot);
});

function jsonResponse(payload: IndustryHierarchyView) {
  return new Response(JSON.stringify(payload), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}
