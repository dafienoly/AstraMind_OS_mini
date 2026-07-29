import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { StockSearchCombobox } from "./StockSearchCombobox";

const originalFetch = globalThis.fetch;

describe("StockSearchCombobox", () => {
  beforeEach(() => {
    globalThis.fetch = vi.fn(async () => new Response(JSON.stringify([
      {
        instrument_id: "000001.SZ",
        instrument_name: "平安银行",
        instrument_type: "stock",
        last_price: 11.28,
        change_percent: 0.71,
        status_label: "正常交易",
      },
    ]), { status: 200, headers: { "Content-Type": "application/json" } }));
  });

  afterEach(() => {
    cleanup();
    globalThis.fetch = originalFetch;
  });

  it("matches by name and adds the selected result with the keyboard", async () => {
    const onAdd = vi.fn();
    render(<StockSearchCombobox onAdd={onAdd} watchlist={[]} />);

    const input = screen.getByRole("combobox");
    fireEvent.change(input, { target: { value: "平安" } });
    await screen.findByRole("option", { name: /平安银行.*000001\.SZ/ });
    fireEvent.keyDown(input, { key: "Enter" });

    expect(onAdd).toHaveBeenCalledWith("000001.SZ");
    expect(input).toHaveValue("");
  });

  it("supports code fragments and marks existing watchlist entries", async () => {
    render(<StockSearchCombobox onAdd={vi.fn()} watchlist={["000001.SZ"]} />);

    fireEvent.change(screen.getByRole("combobox"), { target: { value: "0000" } });

    expect(await screen.findByText("已在自选")).toBeInTheDocument();
    expect(String((globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls[0][0]))
      .toContain("q=0000");
  });
});
