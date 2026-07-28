import { memo } from "react";

import type { Quadrant, RotationPoint } from "./rotationTypes";
import { quadrantLabels } from "./rotationTypes";

interface RotationChartProps {
  current: RotationPoint[];
  trails: RotationPoint[];
  selectedCode: string;
  dimmedCodes: Set<string>;
  onSelect: (code: string) => void;
}

const MIN = 85;
const SPAN = 30;

function position(value: number) {
  return `${Math.max(0, Math.min(100, ((value - MIN) / SPAN) * 100))}%`;
}

function trailPath(points: RotationPoint[]) {
  return points
    .map((point, index) => {
      const x = ((point.relative_trend - MIN) / SPAN) * 1000;
      const y = 620 - ((point.relative_momentum - MIN) / SPAN) * 620;
      return `${index === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
}

function quadrantClass(quadrant: Quadrant) {
  return `rotation-node rotation-node--${quadrant}`;
}

export const RotationChart = memo(function RotationChart({
  current,
  trails,
  selectedCode,
  dimmedCodes,
  onSelect,
}: RotationChartProps) {
  return (
    <section className="rotation-plot" aria-label="行业相对轮动四象限">
      <div className="quadrant quadrant--improving">
        <strong>弱势改善</strong><span>趋势偏弱 · 动量回升</span>
      </div>
      <div className="quadrant quadrant--leading">
        <strong>强势领先</strong><span>趋势偏强 · 动量增强</span>
      </div>
      <div className="quadrant quadrant--lagging">
        <strong>弱势落后</strong><span>趋势偏弱 · 动量减弱</span>
      </div>
      <div className="quadrant quadrant--weakening">
        <strong>强势降温</strong><span>趋势偏强 · 动量回落</span>
      </div>
      <span className="axis-label axis-label--x">相对趋势 →</span>
      <span className="axis-label axis-label--y">相对动量 →</span>
      <svg className="rotation-trail" viewBox="0 0 1000 620" aria-hidden="true">
        {trails.length > 1 ? <path d={trailPath(trails)} /> : null}
      </svg>
      {current.map((point) => (
        <button
          type="button"
          key={point.industry_code}
          className={[
            quadrantClass(point.quadrant),
            point.industry_code === selectedCode ? "is-selected" : "",
            dimmedCodes.has(point.industry_code) ? "is-dimmed" : "",
          ].join(" ")}
          style={{
            left: position(point.relative_trend),
            bottom: position(point.relative_momentum),
          }}
          aria-label={`${point.industry_name}，${point.trade_date}，相对趋势 ${point.relative_trend.toFixed(2)}，相对动量 ${point.relative_momentum.toFixed(2)}，${quadrantLabels[point.quadrant]}`}
          onClick={() => onSelect(point.industry_code)}
        >
          <i aria-hidden="true" />
          <span>{point.industry_name}</span>
        </button>
      ))}
    </section>
  );
});
