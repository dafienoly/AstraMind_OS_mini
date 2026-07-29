import { RotationChart } from "./RotationChart";
import { RotationFormulaDrawer } from "./RotationFormulaDrawer";
import { Inspector, Playback, RotationHeader } from "./RotationPanels";
import { RotationToolbar } from "./RotationToolbar";
import { IndustryHierarchyExplorer } from "./IndustryHierarchyExplorer";
import type {
  RotationScreenRow,
  RotationSortKey,
  RotationSortOrder,
} from "./rotationScreening";
import type {
  MotionState,
  Quadrant,
  ContinuousDuration,
  PlaybackMode,
  RotationPoint,
  RotationSnapshot,
  RotationSpeed,
  RotationTrail,
  TrailMode,
  VisualRotationPoint,
} from "./rotationTypes";

export interface RotationReadyViewProps {
  snapshot: RotationSnapshot;
  current: RotationPoint[];
  visualCurrent: VisualRotationPoint[];
  trails: RotationTrail[];
  selected: string;
  dimmed: Set<string>;
  dateIndex: number;
  currentDate: string;
  playing: boolean;
  reducedMotion: boolean;
  progress: number;
  speed: RotationSpeed;
  trail: number;
  search: string;
  quadrant: Quadrant | "";
  motion: MotionState | "";
  sort: RotationSortKey;
  order: RotationSortOrder;
  recentOnly: boolean;
  onlySelected: boolean;
  trailMode: TrailMode;
  formulaOpen: boolean;
  counts: Record<string, number>;
  screenRows: RotationScreenRow[];
  goToDate: (index: number) => void;
  onSelect: (value: string) => void;
  onSearch: (value: string) => void;
  onQuadrant: (value: Quadrant | "") => void;
  onMotion: (value: MotionState | "") => void;
  onSort: (value: RotationSortKey) => void;
  onOrder: (value: RotationSortOrder) => void;
  onScreenReset: () => void;
  onRecentOnly: (value: boolean) => void;
  onRefresh: () => void;
  onOnlySelected: (value: boolean) => void;
  onTrailMode: (value: TrailMode) => void;
  onFormulaToggle: () => void;
  onPlayToggle: () => void;
  playbackMode: PlaybackMode;
  onPlaybackMode: (value: PlaybackMode) => void;
  continuousDuration: ContinuousDuration;
  onContinuousDuration: (value: ContinuousDuration) => void;
  hierarchyParent: string;
  refreshing: boolean;
  onHierarchyParent: (value: string) => void;
  setSpeed: (value: RotationSpeed) => void;
  setTrail: (value: number) => void;
}

export function RotationReadyView(props: RotationReadyViewProps) {
  const selectedPoint =
    props.current.find((point) => point.industry_code === props.selected)
    ?? undefined;
  const event = [...props.snapshot.events].reverse().find(
    (item) =>
      item.industry_code === props.selected
      && item.confirmed_date <= props.currentDate,
  );
  return (
    <div className="rotation-app">
      <RotationHeader
        onRefresh={props.onRefresh}
        refreshing={props.refreshing}
        snapshot={props.snapshot}
      />
      <main className="rotation-main">
        <div className="market-tabs" aria-label="市场视图">
          <span>大盘</span><strong>行业</strong><span>ETF 轮动</span>
          <i /><span>行业热力</span><strong>相对轮动</strong>
        </div>
        {props.hierarchyParent ? (
          <IndustryHierarchyExplorer
            asOf={props.currentDate}
            onBack={() => props.onHierarchyParent("")}
            parentCode={props.hierarchyParent}
            parentName={selectedPoint?.industry_name ?? props.hierarchyParent}
            onRefresh={props.onRefresh}
            refreshing={props.refreshing}
            snapshot={props.snapshot}
          />
        ) : <>
        <RotationToolbar
          counts={props.counts}
          formulaOpen={props.formulaOpen}
          industries={props.current}
          rows={props.screenRows}
          onlySelected={props.onlySelected}
          onFormulaToggle={props.onFormulaToggle}
          onOnlySelected={props.onOnlySelected}
          onQuadrant={props.onQuadrant}
          onMotion={props.onMotion}
          onSort={props.onSort}
          onOrder={props.onOrder}
          onScreenReset={props.onScreenReset}
          onRecentOnly={props.onRecentOnly}
          onSearch={props.onSearch}
          onSelect={props.onSelect}
          onTrailMode={props.onTrailMode}
          quadrant={props.quadrant}
          motion={props.motion}
          sort={props.sort}
          order={props.order}
          recentOnly={props.recentOnly}
          search={props.search}
          selected={props.selected}
          trailMode={props.trailMode}
        />
        {props.selected && !props.screenRows.some((row) => row.code === props.selected) ? (
          <p className="rotation-selection-filtered">
            当前选择不在筛选结果中，检查器仍保留。
          </p>
        ) : null}
        <div className="rotation-workspace">
          <div>
            <RotationChart
              current={props.visualCurrent}
              dimmedCodes={props.dimmed}
              onSelect={props.onSelect}
              onClear={() => props.onSelect("")}
              history={props.snapshot.points}
              progress={props.progress}
              selectedCode={props.selected}
              trails={props.trails}
            />
            <Playback
              dateIndex={props.dateIndex}
              dates={props.snapshot.dates}
              goToDate={props.goToDate}
              playing={props.playing}
              reducedMotion={props.reducedMotion}
              onPlayToggle={props.onPlayToggle}
              mode={props.playbackMode}
              onMode={props.onPlaybackMode}
              continuousDuration={props.continuousDuration}
              onContinuousDuration={props.onContinuousDuration}
              setSpeed={props.setSpeed}
              setTrail={props.setTrail}
              speed={props.speed}
              trail={props.trail}
            />
          </div>
          {props.formulaOpen ? (
            <RotationFormulaDrawer
              onClose={props.onFormulaToggle}
              snapshot={props.snapshot}
            />
          ) : (
            <Inspector
              event={event}
              onDrill={selectedPoint
                ? () => props.onHierarchyParent(selectedPoint.industry_code)
                : undefined}
              point={selectedPoint}
              snapshot={props.snapshot}
            />
          )}
        </div>
        </>}
      </main>
    </div>
  );
}
