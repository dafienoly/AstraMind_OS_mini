import { HierarchyCoverageNotice } from "./HierarchyCoverageNotice";
import { HierarchyPlot } from "./HierarchyPlot";
import { RotationRankedList } from "./RotationRankedList";
import { RotationScreeningControls } from "./RotationScreeningControls";
import { StockRotationFocusToolbar } from "./StockRotationFocusToolbar";
import type { IndustryHierarchyView } from "./rotationTypes";
import { useStockRotationNavigator } from "./useStockRotationNavigator";

export function StockRotationNavigator({
  view,
  selected,
  onInstrument,
}: {
  view: IndustryHierarchyView;
  selected: string;
  onInstrument: (code: string) => void;
}) {
  const state = useStockRotationNavigator(view, selected, onInstrument);
  return <section className="stock-navigator" aria-label="个股轮动与成分">
    <header>
      <div>
        <p className="eyebrow">个股相对轮动</p>
        <strong>点击节点，股票证据同步切换</strong>
      </div>
      <button
        aria-expanded={state.expanded}
        className="stock-rotation-expand"
        onClick={() => state.setExpanded(true)}
        type="button"
      >
        展开聚焦
      </button>
    </header>
    {state.expanded ? <StockRotationFocusToolbar
      onCenter={() => state.setViewport({ centerX: 50, centerY: 50, zoom: 1 })}
      onCollapse={state.collapse}
      onFit={state.fit}
      onTrailLength={state.setTrailLength}
      onZoom={state.zoom}
      trailLength={state.trailLength}
      zoom={state.viewport.zoom}
    /> : null}
    <div
      aria-label={state.expanded ? "个股轮动聚焦导航" : undefined}
      className="stock-rotation-stage"
      onKeyDown={state.expanded ? state.onKeyDown : undefined}
      tabIndex={state.expanded ? 0 : undefined}
    >
      {view.rotation ? <HierarchyPlot
        ariaLabel="个股相对轮动四象限"
        focusedCode={state.expanded ? state.focusedCode : ""}
        onSelect={onInstrument}
        onViewportChange={state.expanded ? state.setViewport : undefined}
        selectedCode={selected}
        showPointDetails={state.expanded}
        snapshot={view.rotation}
        trailLength={state.trailLength}
        trailMode="selected"
        viewport={state.viewport}
        visibleCodes={state.visibleCodes}
      /> : null}
      {state.expanded ? <RotationRankedList
        focusedCode={state.focusedCode}
        label="可读索引"
        onFocus={state.setFocusedCode}
        onReset={state.screening.onReset}
        onSelect={onInstrument}
        rows={state.rows}
        selectedCode={selected}
      /> : null}
    </div>
    {state.expanded ? <p className="stock-rotation-keyboard-help">
      拖动画布平移；↑/↓ 聚焦对象，Enter 选中，Esc 收起。
    </p> : null}
    <HierarchyCoverageNotice view={view} />
    <RotationScreeningControls
      {...state.screening}
      resultCount={state.rows.length}
      showSearch
      totalCount={view.nodes.length}
      urlPrefix="个股"
    />
    {state.selectionFiltered ? <p className="rotation-selection-filtered">
      当前选择不在筛选结果中，股票证据仍保留。
    </p> : null}
    {!state.expanded ? <RotationRankedList
      label="当日有效成分股"
      onReset={state.screening.onReset}
      onSelect={onInstrument}
      rows={state.rows}
      selectedCode={selected}
    /> : null}
  </section>;
}
