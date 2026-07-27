import { render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import { App } from "./App";

afterEach(() => {
  vi.restoreAllMocks();
});

test("shows that the product UI is not implemented and broker is off", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(JSON.stringify({ version: "0.1.0", broker_enabled: false }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    }),
  );

  render(<App />);

  expect(screen.getByRole("heading", { name: "产品界面尚未实现" })).toBeInTheDocument();
  expect(await screen.findByText(/已连接.*券商关闭/)).toBeInTheDocument();
});
