import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { TechnicalDetails } from "./TechnicalDetails";

describe("TechnicalDetails", () => {
  it("keeps raw values in an explicitly diagnostic, collapsed region", () => {
    const contentIdentity = `sha256:${"a".repeat(64)}`;
    const gapCode = "historical_membership_not_then_known";
    render(<TechnicalDetails entries={[
      { label: "内容身份", value: contentIdentity },
      { label: "缺口代码", value: [gapCode] },
    ]} />);

    const details = screen.getByLabelText("技术详情");
    expect(details).not.toHaveAttribute("open");
    expect(screen.getByText("技术详情")).toBeVisible();
    expect(screen.getByText(contentIdentity)).not.toBeVisible();
    expect(screen.getByText(gapCode)).not.toBeVisible();

    fireEvent.click(screen.getByText("技术详情"));

    expect(details).toHaveAttribute("open");
    expect(screen.getByText("以下原始值仅用于诊断，不代表业务结论。")).toBeVisible();
    expect(screen.getByText(contentIdentity)).toBeVisible();
    expect(screen.getByText(gapCode)).toBeVisible();
  });
});
