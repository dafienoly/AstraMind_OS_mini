import { useEffect, useState } from "react";

import type { IndustryHierarchyView } from "./rotationTypes";
import { StockEvidencePanel } from "./StockEvidencePanel";
import { StockPriceWorkbench } from "./StockPriceWorkbench";
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
  const [hoverDate, setHoverDate] = useState(view.as_of);
  useEffect(() => setHoverDate(view.as_of), [view.as_of, view.selected_code]);

  return <div
    aria-busy={updatingLabel ? "true" : "false"}
    className="stock-evidence-workbench"
  >
    {refreshError ? (
      <p className="stock-update-error" role="alert">
        股票证据切换失败：{refreshError}。当前仍显示上一只股票；再次点击目标节点可重试。
      </p>
    ) : null}
    <StockRotationNavigator onInstrument={onInstrument} selected={selected} view={view} />
    <StockPriceWorkbench
      onHoverDate={setHoverDate}
      updatingLabel={updatingLabel}
      view={view}
    />
    <StockEvidencePanel
      evidence={view.stock_evidence}
      hoverDate={hoverDate}
      updatingLabel={updatingLabel}
    />
  </div>;
}
