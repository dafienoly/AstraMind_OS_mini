import { motionLabels } from "./rotationIdentity";
import type { RotationScreenRow } from "./rotationScreening";

export function RotationRankedList({
  rows,
  selectedCode,
  label,
  onSelect,
  onReset,
  focusedCode,
  onFocus,
}: {
  rows: RotationScreenRow[];
  selectedCode: string;
  label: string;
  onSelect: (code: string) => void;
  onReset: () => void;
  focusedCode?: string;
  onFocus?: (code: string) => void;
}) {
  return <aside className="hierarchy-list rotation-ranked-list">
    <p className="eyebrow">{label}</p>
    {rows.length ? <div>
      {rows.map((row, index) => (
        <button
          aria-pressed={row.code === selectedCode}
          className={row.code === focusedCode ? "is-keyboard-focused" : ""}
          key={row.code}
          onFocus={() => onFocus?.(row.code)}
          onClick={() => onSelect(row.code)}
          type="button"
        >
          <b>{index + 1}</b>
          <span><strong>{row.name}</strong><code>{row.code}</code></span>
          {row.point ? <small>
            X {row.point.relative_trend.toFixed(2)} ·
            Y {row.point.relative_momentum.toFixed(2)} ·
            速度 {row.speed?.toFixed(2) ?? "—"} · {motionLabels[row.motion]}
          </small> : <small>轮动坐标不可用 · {motionLabels[row.motion]}</small>}
        </button>
      ))}
    </div> : <div className="rotation-screen-empty">
      <strong>没有符合当前条件的对象</strong>
      <span>筛选结果不会自动回退为全部对象。</span>
      <button onClick={onReset} type="button">重置筛选</button>
    </div>}
  </aside>;
}
