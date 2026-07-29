import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { MarketStatusStrip } from "./MarketChrome";
import type { MarketDashboardProjection } from "./types";

describe("MarketStatusStrip business language", () => {
  it("shows update time while keeping snapshot identity and gap codes collapsed", () => {
    const snapshotId = `snapshot:sha256:${"a".repeat(64)}`;
    render(<MarketStatusStrip
      onRefresh={vi.fn()}
      projection={{
        status: "blocked",
        data_snapshot_id: snapshotId,
        as_of: "2026-07-29T18:00:00+08:00",
        evidence_cutoff: "2026-07-29",
        projection_version: "market-dashboard-v1.0.0",
        selected_index_id: null,
        indexes: [],
        breadth: null,
        liquidity: null,
        regime: null,
        industries: [],
        known_gaps: ["historical_membership_not_then_known"],
      } satisfies MarketDashboardProjection}
      refreshing={false}
    />);

    expect(screen.getByText(/数据版本/)).toBeVisible();
    expect(screen.getByText(/更新至 2026-07-29/)).toBeVisible();
    const details = screen.getByLabelText("技术详情");
    expect(details).not.toHaveAttribute("open");
    expect(screen.getByText(snapshotId)).not.toBeVisible();
    expect(screen.getByText("historical_membership_not_then_known")).not.toBeVisible();
  });
});
