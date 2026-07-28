import { render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import { App } from "./App";

afterEach(() => {
  vi.restoreAllMocks();
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
