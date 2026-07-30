import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import { fallbackModelStatus } from "./market-dashboard/model-evidence/testSupport";
import { App } from "./App";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  window.history.replaceState(null, "", "/");
});

test("shows the local workstation entry and broker is off", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(JSON.stringify({ version: "0.1.0", broker_enabled: false }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    }),
  );

  render(<App />);

  expect(screen.getByRole("heading", { name: "本地量化交易工作台" })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "进入市场 · 行业相对轮动" })).toBeInTheDocument();
  expect(await screen.findByText(/已连接.*券商关闭/)).toBeInTheDocument();
});

test("routes the approved System method-status page through the shared shell", async () => {
  window.history.replaceState(null, "", "/system/method-status");
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(JSON.stringify(fallbackModelStatus()), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    }),
  );

  render(<App />);

  expect(await screen.findByRole("heading", { name: "当前为什么使用这个方法？" }))
    .toBeInTheDocument();
  expect(screen.getByRole("navigation", { name: "系统视图" })).toBeInTheDocument();
  expect(screen.getAllByRole("navigation", { name: "一级导航" })).toHaveLength(1);
});
