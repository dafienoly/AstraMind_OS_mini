import type { IndustryHierarchyView } from "./rotationTypes";
import { stockWorkbenchHref } from "../stock-workbench/focus";
import { StockRotationNavigator } from "./StockRotationNavigator";

export function StockHierarchyWorkbench({
  view,
  onInstrument,
  pendingInstrument,
  refreshError,
}: {
  view: IndustryHierarchyView;
  onInstrument: (code: string) => void;
  pendingInstrument?: string;
  refreshError?: string;
}) {
  const selected = pendingInstrument || view.selected_code || "";
  const pendingName = view.nodes.find((node) => node.code === pendingInstrument)?.name;
  const updatingLabel = pendingInstrument
    ? `正在切换至 ${pendingName ?? pendingInstrument}`
    : undefined;
  return <div
    aria-busy={updatingLabel ? "true" : "false"}
    className="stock-evidence-workbench"
  >
    {refreshError ? (
      <p className="stock-update-error" role="alert">
        股票证据切换失败：{refreshError}。当前仍显示上一只股票；再次点击目标节点可重试。
      </p>
    ) : null}
    {updatingLabel ? <p className="stock-update-status" role="status">{updatingLabel}</p> : null}
    <StockRotationNavigator onInstrument={onInstrument} selected={selected} view={view} />
    <aside className="stock-workbench-entry">
      <p className="eyebrow">统一个股证据</p>
      <h2>{view.stock_evidence?.instrument_name ?? (selected || "选择股票")}</h2>
      <p>行业页只保留比较与选择；价格、分钟成交、五档盘口、估值和股东证据由通用个股工作面统一呈现。</p>
      {selected ? <a href={stockWorkbenchHref(selected, {
        origin: "industry_rotation",
        mode: "completed",
        returnTarget: "industry_rotation",
        dataSnapshotId: view.data_snapshot_id,
        asOf: view.as_of,
        industryCode: view.parent_code ?? undefined,
      })}>打开通用个股工作面 →</a> : null}
    </aside>
  </div>;
}
