import { fireEvent, render, screen } from "@testing-library/react";
import { expect, test } from "vitest";

import { UiLab } from "./UiLab";
import {
  aggregateCandles,
  buildCandleFixture,
  decisionCutoff,
  visibleAt,
} from "./market/candleFixture";

test("future fixture rows never cross the decision cutoff", () => {
  const fixture = buildCandleFixture();
  const visible = visibleAt(fixture, decisionCutoff);
  expect(fixture.some((item) => item.time > decisionCutoff)).toBe(true);
  expect(visible.every((item) => item.time <= decisionCutoff)).toBe(true);
  expect(aggregateCandles(visible, "月线").every((item) => item.time <= decisionCutoff)).toBe(true);
});

test("UI Lab exposes the chart workflow and important states", () => {
  render(<UiLab />);
  expect(screen.getByRole("heading", { name: "统一价格检查器" })).toBeInTheDocument();
  expect(screen.getByText("未来数据已隔离")).toBeInTheDocument();
  expect(screen.getByText("数据陈旧")).toBeInTheDocument();
  expect(screen.getByTestId("dual-range")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "周线" }));
  expect(screen.getByRole("button", { name: "周线" })).toHaveClass("active");
});
