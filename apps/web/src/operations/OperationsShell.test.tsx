import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import { OperationsShell } from "./OperationsShell";
import type { DailyOperations, PaperOperations } from "./types";

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

const dailyFixture: DailyOperations = {
  as_of: "2026-07-28T10:30:00Z",
  pipeline: {
    target_date: "2026-07-27",
    state: "current",
    observed_l1_count: 31,
    observed_l2_count: 124,
    blocker_codes: [],
    recovery_action: null,
    broker_actions_allowed: false,
  },
  decision: {
    signal_date: "2026-07-27",
    state: "current",
    shadow_preflight_state: "ready",
    paper_preflight_state: "ready",
    blocker_codes: [],
    recovery_action: null,
    paper_dispatch_state: "disabled",
    broker_actions_allowed: false,
  },
  latest_run: {
    run_id: "daily-run:test",
    target_date: "2026-07-27",
    base_snapshot_id: "snapshot:test",
    state: "current",
    current_step: null,
    data_commit_id: "commit:test",
    data_snapshot_id: "snapshot:test",
    rotation_snapshot_id: "rotation:test",
    feature_snapshot_id: "feature:test",
    prediction_batch_id: "prediction:test",
    portfolio_target_id: "target:test",
    order_plan_id: "order:test",
    backup_id: "backup:test",
    blocker_codes: [],
    recovery_action: null,
    started_at: "2026-07-28T09:00:00Z",
    updated_at: "2026-07-28T09:05:00Z",
    completed_at: "2026-07-28T09:05:00Z",
    broker_actions_allowed: false,
  },
  recent_runs: [],
  schedule: {
    state: "installed",
    task_name: "AstraMind OS Mini - Daily Ops",
    trigger_labels: ["每日 16:35 首次运行"],
    next_run_at: "2026-07-29T08:35:00Z",
    last_result: "0",
    updated_at: "2026-07-28T10:00:00Z",
    broker_actions_allowed: false,
  },
  pending_request: null,
  attention: [],
  broker_actions_allowed: false,
};

afterEach(() => vi.restoreAllMocks());

test("execution workbench shows exact canary boundary without a submit control", async () => {
  vi.spyOn(globalThis, "fetch").mockImplementation(optionalStatusMissing);

  render(<OperationsShell destination="execution" />);

  expect(await screen.findByRole("heading", { name: "一笔金丝雀，一条恢复路径" })).toBeVisible();
  expect(screen.getByText("605208.SH")).toBeVisible();
  expect(screen.getByText("等待窗口内确认")).toBeVisible();
  expect(screen.queryByRole("button", { name: /提交|买入/ })).not.toBeInTheDocument();
  expect(screen.getByText("未确认时只查询恢复，不自动重提。")).toBeVisible();
});

test("system workbench refreshes the read-only local projection", async () => {
  const fetch = vi.spyOn(globalThis, "fetch").mockImplementation(optionalStatusMissing);
  render(<OperationsShell destination="system" />);
  await screen.findByRole("heading", { name: "只显示今天是否可运行" });

  fireEvent.click(screen.getByRole("button", { name: "刷新本地投影" }));

  expect(fetch).toHaveBeenCalledTimes(4);
  expect(screen.getByRole("heading", { name: "只显示今天是否可运行" })).toBeVisible();
});

test("system workbench shows daily data and decision status without broker controls", async () => {
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    const url = String(input);
    if (url.endsWith("/api/system/daily-operations")) return response(dailyFixture);
    return response(fixture);
  });
  render(<OperationsShell destination="system" />);

  expect(await screen.findByText("2026-07-27 · L1 31 / L2 124")).toBeVisible();
  expect(screen.getByText("2026-07-27 · Shadow ready / Paper ready")).toBeVisible();
  expect(screen.getByText("2026-07-27 · 已完成")).toBeVisible();
  expect(screen.queryByRole("button", { name: /提交|下单|撤单/ })).not.toBeInTheDocument();
});

test("today inbox registers one local recovery request without a broker action", async () => {
  const blockedDaily = {
    ...dailyFixture,
    attention: [{
      code: "daily_run_recovery_required",
      severity: "warning",
      title: "日常运行需要恢复",
      detail: "恢复同一运行",
      action: "recover",
    }],
  } satisfies DailyOperations;
  const fetch = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = String(input);
    if (url.endsWith("/api/system/daily-operations")) return response(blockedDaily);
    if (url.endsWith("/api/system/daily-run-requests")) {
      expect(init?.method).toBe("POST");
      expect(init?.headers).toMatchObject({ "X-AstraMind-Local-Action": "daily-ops-v1" });
      expect(String(init?.body)).toContain('"action":"recover"');
      return response({ request_id: "daily-run-request:test" });
    }
    return response(fixture);
  });
  render(<OperationsShell destination="today" />);

  fireEvent.click(await screen.findByRole("button", { name: "登记恢复" }));

  expect(fetch).toHaveBeenCalledWith(
    expect.stringContaining("/api/system/daily-run-requests"),
    expect.objectContaining({ method: "POST" }),
  );
  expect(screen.queryByRole("button", { name: /提交|下单|撤单/ })).not.toBeInTheDocument();
});

async function optionalStatusMissing(input: RequestInfo | URL) {
  const url = String(input);
  if (url.includes("/api/system/")) return new Response("", { status: 404 });
  return response(fixture);
}

function response(value: object) {
  return new Response(JSON.stringify(value), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}
