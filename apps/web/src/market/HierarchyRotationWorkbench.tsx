import { useMemo } from "react";

import { HierarchyCoverageNotice } from "./HierarchyCoverageNotice";
import { HierarchyPlot } from "./HierarchyPlot";
import { RotationRankedList } from "./RotationRankedList";
import { RotationScreeningControls } from "./RotationScreeningControls";
import {
  buildRotationScreenRows,
  recentRotationEventCodes,
} from "./rotationScreening";
import type { IndustryHierarchyView } from "./rotationTypes";
import { useHierarchyScreening } from "./useHierarchyScreening";

export function HierarchyRotationWorkbench({
  view,
  selectedCode,
  onSelect,
}: {
  view: IndustryHierarchyView;
  selectedCode: string;
  onSelect: (code: string) => void;
}) {
  const screening = useHierarchyScreening("l2_");
  const currentDate = view.rotation?.dates.at(-1);
  const current = useMemo(
    () => view.rotation?.points.filter((point) => point.trade_date === currentDate) ?? [],
    [view.rotation, currentDate],
  );
  const eventCodes = useMemo(
    () => recentRotationEventCodes(view.rotation, currentDate ?? ""),
    [view.rotation, currentDate],
  );
  const rows = useMemo(() => buildRotationScreenRows({
    identities: view.nodes,
    current,
    history: view.rotation?.points ?? [],
    options: screening,
  }).filter((row) => !screening.recentOnly || eventCodes.has(row.code)),
  [view.nodes, view.rotation, current, screening, eventCodes]);
  const visibleCodes = useMemo(
    () => new Set(rows.map((row) => row.code)),
    [rows],
  );
  const selectionFiltered = selectedCode
    && !visibleCodes.has(selectedCode);
  return <>
    <RotationScreeningControls
      {...screening}
      resultCount={rows.length}
      showSearch
      totalCount={view.nodes.length}
      urlPrefix="二级行业"
    />
    {selectionFiltered ? (
      <p className="rotation-selection-filtered">当前选择不在筛选结果中，详情仍保留。</p>
    ) : null}
    {view.rotation ? <HierarchyPlot
      onSelect={onSelect}
      selectedCode={selectedCode}
      snapshot={view.rotation}
      visibleCodes={visibleCodes}
    /> : null}
    <RotationRankedList
      label={view.level === "L2" ? "二级行业" : "历史有效成分股"}
      onReset={screening.onReset}
      onSelect={onSelect}
      rows={rows}
      selectedCode={selectedCode}
    />
    <HierarchyCoverageNotice view={view} />
  </>;
}
