import { act, cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import { AppShell } from "./AppShell";
import { useRouteLoadPhase } from "./routeProgress";
import type { AppLocation } from "./types";

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  window.history.replaceState(null, "", "/");
});

test("owns the only five first-level destinations on every market subpage", () => {
  const location: AppLocation = {
    pathname: "/market",
    search: "?tab=etf",
    key: "/market?tab=etf",
  };
  render(<AppShell location={location}><Ready /></AppShell>);

  const navigation = screen.getByRole("navigation", { name: "一级导航" });
  expect(within(navigation).getAllByRole("link")).toHaveLength(5);
  expect(within(navigation).getByRole("link", { name: "市场" }))
    .toHaveAttribute("aria-current", "page");
  expect(screen.getByRole("link", { name: "ETF 轮动" }))
    .toHaveAttribute("aria-current", "page");
  expect(screen.getAllByRole("navigation", { name: "一级导航" })).toHaveLength(1);
});

test("keeps the stable three-item System navigation on the method page", () => {
  const location: AppLocation = {
    pathname: "/system/method-status",
    search: "",
    key: "/system/method-status",
  };
  render(<AppShell location={location}><Ready /></AppShell>);

  const primary = screen.getByRole("navigation", { name: "一级导航" });
  expect(within(primary).getAllByRole("link")).toHaveLength(5);
  expect(within(primary).getByRole("link", { name: "系统" }))
    .toHaveAttribute("aria-current", "page");
  const system = screen.getByRole("navigation", { name: "系统视图" });
  expect(within(system).getAllByRole("link").map((link) => link.textContent)).toEqual([
    "数据与作业",
    "方法与状态",
    "执行与恢复",
  ]);
  expect(within(system).getByRole("link", { name: "方法与状态" }))
    .toHaveAttribute("aria-current", "page");
});

test("shows a progress bar immediately and a slow-route skeleton after 300ms", () => {
  vi.useFakeTimers();
  const location: AppLocation = {
    pathname: "/market",
    search: "?tab=stocks",
    key: "/market?tab=stocks",
  };
  render(<AppShell location={location}><Loading /></AppShell>);

  expect(document.querySelector(".route-progress")).toHaveClass("is-active");
  expect(document.querySelector(".route-loading-overlay")).not.toBeInTheDocument();
  act(() => vi.advanceTimersByTime(301));
  expect(document.querySelector(".route-loading-overlay")).toHaveAttribute("aria-busy", "true");
  expect(screen.getByRole("status")).toHaveTextContent("正在读取本地自选");
});

function Ready() {
  useRouteLoadPhase("ready", "完成");
  return <main>ready</main>;
}

function Loading() {
  useRouteLoadPhase("loading_content", "正在读取本地自选");
  return <main>loading</main>;
}
