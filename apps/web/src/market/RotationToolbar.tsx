import { IndustryCombobox } from "./IndustryCombobox";
import { RotationScreeningControls } from "./RotationScreeningControls";
import type {
  RotationScreenRow,
  RotationSortKey,
  RotationSortOrder,
} from "./rotationScreening";
import type {
  MotionState,
  Quadrant,
  RotationPoint,
  TrailMode,
} from "./rotationTypes";

const trailModes: { value: TrailMode; label: string }[] = [
  { value: "selected", label: "选中行业" },
  { value: "filtered", label: "筛选结果" },
  { value: "all", label: "全部行业" },
];

export function RotationToolbar(props: {
  industries: RotationPoint[];
  rows: RotationScreenRow[];
  selected: string;
  search: string;
  quadrant: Quadrant | "";
  motion: MotionState | "";
  sort: RotationSortKey;
  order: RotationSortOrder;
  onlySelected: boolean;
  recentOnly: boolean;
  trailMode: TrailMode;
  formulaOpen: boolean;
  counts: Record<string, number>;
  onSelect: (value: string) => void;
  onSearch: (value: string) => void;
  onQuadrant: (value: Quadrant | "") => void;
  onMotion: (value: MotionState | "") => void;
  onSort: (value: RotationSortKey) => void;
  onOrder: (value: RotationSortOrder) => void;
  onScreenReset: () => void;
  onOnlySelected: (value: boolean) => void;
  onRecentOnly: (value: boolean) => void;
  onTrailMode: (value: TrailMode) => void;
  onFormulaToggle: () => void;
}) {
  return (
    <section className="rotation-tools" aria-label="轮动筛选">
      <IndustryCombobox
        industries={props.industries}
        rows={props.rows}
        onSearch={props.onSearch}
        onSelect={props.onSelect}
        search={props.search}
        selectedCode={props.selected}
      />
      <RotationScreeningControls
        motion={props.motion}
        onMotion={props.onMotion}
        onOrder={props.onOrder}
        onQuadrant={props.onQuadrant}
        onReset={props.onScreenReset}
        onSearch={props.onSearch}
        onSort={props.onSort}
        order={props.order}
        quadrant={props.quadrant}
        recentOnly={props.recentOnly}
        resultCount={props.rows.length}
        search={props.search}
        sort={props.sort}
        totalCount={props.industries.length}
        onRecentOnly={props.onRecentOnly}
      />
      <fieldset className="trail-mode">
        <legend>轨迹</legend>
        {trailModes.map((item) => (
          <button
            aria-pressed={props.trailMode === item.value}
            key={item.value}
            onClick={() => props.onTrailMode(item.value)}
            type="button"
          >
            {item.label}
          </button>
        ))}
      </fieldset>
      <label><input type="checkbox" checked={props.onlySelected}
        onChange={(event) => props.onOnlySelected(event.target.checked)} />仅选中</label>
      <button
        aria-expanded={props.formulaOpen}
        className="formula-trigger"
        onClick={props.onFormulaToggle}
        type="button"
      >
        公式与口径
      </button>
      <span className="quadrant-counts">
        领先 {props.counts.leading} · 降温 {props.counts.weakening} ·
        落后 {props.counts.lagging} · 改善 {props.counts.improving}
      </span>
    </section>
  );
}
