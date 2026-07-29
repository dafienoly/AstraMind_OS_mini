import { RotationChart } from "./RotationChart";
import { visualPoint } from "./rotationPlayback";
import { buildRotationTrails } from "./rotationTrails";
import type { RotationSnapshot, TrailMode } from "./rotationTypes";
import type { RotationViewport } from "./rotationViewport";

export function HierarchyPlot({
  snapshot,
  selectedCode,
  onSelect,
  ariaLabel,
  visibleCodes,
  focusedCode,
  showPointDetails,
  trailLength = 20,
  trailMode = "all",
  viewport,
  onViewportChange,
}: {
  snapshot: RotationSnapshot;
  selectedCode: string;
  onSelect: (code: string) => void;
  ariaLabel?: string;
  visibleCodes?: Set<string>;
  focusedCode?: string;
  showPointDetails?: boolean;
  trailLength?: number;
  trailMode?: TrailMode;
  viewport?: RotationViewport;
  onViewportChange?: (viewport: RotationViewport) => void;
}) {
  const dateIndex = snapshot.dates.length - 1;
  const currentDate = snapshot.dates[dateIndex];
  const current = snapshot.points
    .filter((point) => point.trade_date === currentDate)
    .map(visualPoint);
  const visible = visibleCodes ?? new Set(current.map((point) => point.industry_code));
  const dimmed = new Set(current
    .filter((point) => !visible.has(point.industry_code))
    .map((point) => point.industry_code));
  const trails = buildRotationTrails({
    snapshot,
    dateIndex,
    length: trailLength,
    mode: trailMode,
    selectedCode,
    visibleCodes: visible,
    visualCurrent: current,
  });
  return <RotationChart
    ariaLabel={ariaLabel}
    current={current}
    dimmedCodes={dimmed}
    history={snapshot.points}
    focusedCode={focusedCode}
    onClear={() => undefined}
    onSelect={onSelect}
    onViewportChange={onViewportChange}
    progress={0}
    selectedCode={selectedCode}
    showPointDetails={showPointDetails}
    trails={trails}
    viewport={viewport}
  />;
}
