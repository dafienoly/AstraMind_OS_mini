import type { IndustryHierarchyView } from "./rotationTypes";

export interface HierarchyBlockMessage {
  title: string;
  detail: string;
}

export function describeHierarchyBlock(
  view: Pick<IndustryHierarchyView, "known_gaps">,
): HierarchyBlockMessage {
  const gaps = view.known_gaps;
  if (gaps.includes("sw2021_l2_not_published")) {
    return {
      title: "二级行业数据尚未发布",
      detail: "当前数据快照不包含 SW2021 二级行业分类或指数。请先刷新快照；若仍未恢复，再检查受控 L2 发布状态。",
    };
  }
  if (gaps.includes("requested_date_after_snapshot")) {
    return {
      title: "请求日期超出当前快照",
      detail: "所选日期晚于数据快照截止日。请回到快照内日期，或刷新到最新完整快照。",
    };
  }
  const missingDatasets = gaps.find((gap) => gap.startsWith("missing_datasets:"));
  if (missingDatasets) {
    return {
      title: "当前快照缺少层级数据",
      detail: `层级查询所需数据集不完整：${missingDatasets.slice("missing_datasets:".length)}。请检查日度管线并重新发布完整快照。`,
    };
  }
  if (gaps.includes("same_level_history_incomplete")) {
    return {
      title: "同层历史数据不完整",
      detail: "当前层级的指数、成员或行情历史不足，无法按冻结公式计算轮动。请检查覆盖报告或切换日期。",
    };
  }
  return {
    title: "行业层级证据已阻断",
    detail: "当前快照无法形成完整的层级研究证据，请查看阻断代码和系统运行状态。",
  };
}
