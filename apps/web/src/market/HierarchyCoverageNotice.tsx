import type { IndustryHierarchyView } from "./rotationTypes";

export function HierarchyCoverageNotice({
  view,
}: {
  view: IndustryHierarchyView;
}) {
  if (view.known_gaps.includes("sibling_cross_section_below_three")) {
    return <p className="hierarchy-readonly">
      父级内已发布二级行业少于 3 个，不能稳定计算同层轮动；仍可继续下钻，
      或切换“全部 L2”比较。
    </p>;
  }
  const excluded = view.known_gaps.find((gap) =>
    gap.startsWith("stock_rotation_incomplete_panel_excluded:"));
  if (!excluded) return null;
  const excludedCount = Number(excluded.split(":", 3)[1]);
  const eligibleCount = view.rotation?.industry_count ?? 0;
  return <p className="hierarchy-readonly">
    个股轮动使用 {eligibleCount}/{view.nodes.length} 个具备至少 141 个交易日的当日有效成分；
    {excludedCount} 个存在新股、停牌等面板缺口的成分仍保留在列表和 K 线中，
    但不进入轮动横截面。
  </p>;
}
