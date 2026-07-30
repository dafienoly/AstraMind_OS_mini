import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { useState } from "react";

import {
  HistoryWindowSelector,
  type PriceHistoryPage,
  type PriceHistoryWindow,
  usePriceHistory,
} from "./priceHistory";

const originalFetch = globalThis.fetch;
const snapshotId = `snapshot:sha256:${"1".repeat(64)}`;
const noBars: [] = [];

afterEach(() => {
  cleanup();
  globalThis.fetch = originalFetch;
});

it("loads a larger window without changing snapshot or evidence cutoff", async () => {
  globalThis.fetch = vi.fn(async () => new Response(JSON.stringify(historyPage()), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  }));
  render(<Harness />);

  fireEvent.click(screen.getByRole("button", { name: "近五年" }));

  expect(await screen.findByText(/2021-07-28 至 2026-07-28/)).toBeInTheDocument();
  expect(globalThis.fetch).toHaveBeenCalledWith(
    expect.stringContaining(
      "window=five_years&data_snapshot_id=snapshot%3Asha256%3A",
    ),
    expect.anything(),
  );
});

it("walks every cursor page and keeps one immutable dataset identity", async () => {
  globalThis.fetch = vi.fn()
    .mockResolvedValueOnce(new Response(JSON.stringify(historyPage({
      bars: [bar("2026-07-28")],
      has_more: true,
      next_cursor: "2026-07-28",
    })), { status: 200, headers: { "Content-Type": "application/json" } }))
    .mockResolvedValueOnce(new Response(JSON.stringify(historyPage({
      bars: [bar("2021-07-28")],
    })), { status: 200, headers: { "Content-Type": "application/json" } }));
  render(<Harness />);

  fireEvent.click(screen.getByRole("button", { name: "近五年" }));

  expect(await screen.findByText(/共 2 根/)).toBeInTheDocument();
  expect(globalThis.fetch).toHaveBeenCalledTimes(2);
  expect(globalThis.fetch).toHaveBeenLastCalledWith(
    expect.stringContaining("cursor=2026-07-28"),
    expect.anything(),
  );
});

function Harness() {
  const [window, setWindow] = useState<PriceHistoryWindow>("one_year");
  const history = usePriceHistory({
    instrumentType: "index",
    instrumentId: "000300.SH",
    dataSnapshotId: snapshotId,
    evidenceCutoff: "2026-07-28",
    window,
    fallback: noBars,
  });
  return <>
    <HistoryWindowSelector onChange={setWindow} state={history.kind} value={window} />
    {history.kind === "ready"
      ? <p>{history.page.coverage_start} 至 {history.page.coverage_end} · 共 {
        history.bars.length
      } 根</p>
      : null}
  </>;
}

function historyPage(overrides: Partial<PriceHistoryPage> = {}): PriceHistoryPage {
  return {
    instrument_type: "index",
    instrument_id: "000300.SH",
    instrument_name: "沪深300",
    data_snapshot_id: snapshotId,
    dataset_name: "broad_index_daily",
    dataset_version: `sha256:${"2".repeat(64)}`,
    dataset_content_hash: `sha256:${"3".repeat(64)}`,
    evidence_cutoff: "2026-07-28",
    window: "five_years",
    requested_start: "2021-07-28",
    requested_end: "2026-07-28",
    coverage_start: "2021-07-28",
    coverage_end: "2026-07-28",
    coverage_basis: "official_launch_or_earliest_reliable_record",
    listing_date: null,
    schema_version: "1.0.0",
    bars: [],
    page_size: 1000,
    has_more: false,
    next_cursor: null,
    known_gaps: [],
    ...overrides,
  };
}

function bar(tradeDate: string) {
  return {
    trade_date: tradeDate,
    open: 1,
    high: 1.1,
    low: 0.9,
    close: 1,
    volume_lots: 100,
    amount_cny: 1_000,
  };
}
