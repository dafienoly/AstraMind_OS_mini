import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import { OperationsShell } from "./OperationsShell";
import type { PaperOperations } from "./types";

const fixture: PaperOperations = {
  as_of: "2026-07-28T04:30:00Z",
  execution_mode: "paper",
  account_mode: "simulation",
  broker_connection: "disconnected",
  canary_state: "blocked",
  standing_mandate_id: "standing-mandate:redacted",
  authorization_id: "paper-canary-authorization:redacted",
  instrument_id: "605208.SH",
  side: "buy",
  quantity: 100,
  max_notional_cny: 50_000,
  mandate_effective_from: "2026-07-29T01:30:00Z",
  mandate_effective_to: "2026-07-29T02:00:00Z",
  submission_window_start: "2026-07-29T01:35:00Z",
  submission_window_end: "2026-07-29T01:45:00Z",
  inherited_overlap: "allowed",
  account_baseline_state: "readonly_ready",
  inherited_position_count: 1,
  open_order_count: 0,
  intent_count: 0,
  observation_count: 0,
  blocker_codes: ["final_limit_approval_required"],
  next_action: "在提交窗口读取新鲜卖一并确认确切限价",
  broker_actions_allowed: false,
};

afterEach(() => vi.restoreAllMocks());

test("execution workbench shows exact canary boundary without a submit control", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(JSON.stringify(fixture), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    }),
  );

  render(<OperationsShell destination="execution" />);

  expect(await screen.findByRole("heading", { name: "一笔金丝雀，一条恢复路径" })).toBeVisible();
  expect(screen.getByText("605208.SH")).toBeVisible();
  expect(screen.getByText("等待窗口内确认")).toBeVisible();
  expect(screen.queryByRole("button", { name: /提交|买入/ })).not.toBeInTheDocument();
  expect(screen.getByText("未确认时只查询恢复，不自动重提。")).toBeVisible();
});

test("system workbench refreshes the read-only local projection", async () => {
  const fetch = vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(JSON.stringify(fixture), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    }),
  );
  render(<OperationsShell destination="system" />);
  await screen.findByRole("heading", { name: "只显示今天是否可运行" });

  fireEvent.click(screen.getByRole("button", { name: "刷新本地投影" }));

  expect(fetch).toHaveBeenCalledTimes(2);
});
