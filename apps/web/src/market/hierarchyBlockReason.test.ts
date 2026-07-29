import { expect, test } from "vitest";

import { describeHierarchyBlock } from "./hierarchyBlockReason";

test.each([
  ["requested_date_after_snapshot", "请求日期超出当前快照"],
  ["missing_datasets:daily_market,security_master", "当前快照缺少层级数据"],
  ["same_level_history_incomplete", "同层历史数据不完整"],
  ["unexpected_gap", "行业层级证据已阻断"],
])("maps hierarchy block reason %s to accurate copy", (reason, title) => {
  expect(describeHierarchyBlock({ known_gaps: [reason] }).title).toBe(title);
});
