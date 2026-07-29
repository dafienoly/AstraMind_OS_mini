import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";

import { HierarchyCoverageNotice } from "./HierarchyCoverageNotice";
import type { IndustryHierarchyView } from "./rotationTypes";

test("discloses short-history members excluded from stock rotation", () => {
  const view = {
    known_gaps: ["stock_rotation_incomplete_panel_excluded:11:codes"],
    nodes: Array.from({ length: 184 }, (_, index) => ({ code: String(index) })),
    rotation: { industry_count: 173 },
  } as IndustryHierarchyView;

  render(<HierarchyCoverageNotice view={view} />);

  expect(screen.getByText(/173\/184 个具备至少 141 个交易日/)).toBeVisible();
  expect(screen.getByText(/11 个存在新股、停牌等面板缺口的成分仍保留/)).toBeVisible();
});
