import { motionLabels } from "./rotationIdentity";
import type {
  RotationScreenOptions,
  RotationSortKey,
  RotationSortOrder,
} from "./rotationScreening";
import type { MotionState, Quadrant } from "./rotationTypes";
import { quadrantLabels } from "./rotationTypes";

const sortLabels: Record<RotationSortKey, string> = {
  name: "名称",
  trend: "相对趋势 X",
  momentum: "相对动量 Y",
  speed: "最新速度",
  distance: "距中心",
};

export function RotationScreeningControls(props: RotationScreenOptions & {
  resultCount: number;
  totalCount: number;
  showSearch?: boolean;
  urlPrefix?: string;
  onSearch: (value: string) => void;
  onQuadrant: (value: Quadrant | "") => void;
  onMotion: (value: MotionState | "") => void;
  onSort: (value: RotationSortKey) => void;
  onOrder: (value: RotationSortOrder) => void;
  onReset: () => void;
  recentOnly?: boolean;
  onRecentOnly?: (value: boolean) => void;
}) {
  const prefix = props.urlPrefix ?? "";
  return <section className="rotation-screening" aria-label="轮动分类筛选与排序">
    {props.showSearch ? <label>
      <span>名称 / 代码</span>
      <input
        aria-label={`${prefix}名称或代码筛选`}
        onChange={(event) => props.onSearch(event.target.value)}
        placeholder="输入名称或代码"
        value={props.search}
      />
    </label> : null}
    <label>
      <span>象限</span>
      <select
        aria-label={`${prefix}象限筛选`}
        onChange={(event) => props.onQuadrant(event.target.value as Quadrant | "")}
        value={props.quadrant}
      >
        <option value="">全部象限</option>
        {Object.entries(quadrantLabels).map(([value, label]) => (
          <option key={value} value={value}>{label}</option>
        ))}
      </select>
    </label>
    {props.onRecentOnly ? <label className="rotation-screening-check">
      <span>事件</span>
      <span><input
        checked={props.recentOnly}
        onChange={(event) => props.onRecentOnly?.(event.target.checked)}
        type="checkbox"
      />近期确认</span>
    </label> : null}
    <label>
      <span>运动</span>
      <select
        aria-label={`${prefix}运动状态筛选`}
        onChange={(event) => props.onMotion(event.target.value as MotionState | "")}
        value={props.motion}
      >
        <option value="">全部运动状态</option>
        {Object.entries(motionLabels).map(([value, label]) => (
          <option key={value} value={value}>{label}</option>
        ))}
      </select>
    </label>
    <label>
      <span>排序</span>
      <select
        aria-label={`${prefix}排序字段`}
        onChange={(event) => props.onSort(event.target.value as RotationSortKey)}
        value={props.sort}
      >
        {Object.entries(sortLabels).map(([value, label]) => (
          <option key={value} value={value}>{label}</option>
        ))}
      </select>
    </label>
    <label>
      <span>方向</span>
      <select
        aria-label={`${prefix}排序方向`}
        onChange={(event) => props.onOrder(event.target.value as RotationSortOrder)}
        value={props.order}
      >
        <option value="asc">升序</option>
        <option value="desc">降序</option>
      </select>
    </label>
    <span className="rotation-screening-actions">
      <strong className="rotation-result-count">
        {props.resultCount} / {props.totalCount} ·
        {props.order === "asc" ? " ↑" : " ↓"}
      </strong>
      <button onClick={props.onReset} type="button">重置</button>
    </span>
  </section>;
}
