import { memo, useMemo } from "react";

import type {
  RotationPoint,
  RotationTrail,
  VisualRotationPoint,
} from "./rotationTypes";
import { RotationNode } from "./RotationNode";
import { RotationLabelLeaders } from "./RotationLabelLeaders";
import { layoutRotationLabels } from "./rotationLabelLayout";
import { projectVisualPoint } from "./rotationProjection";
import { motionState } from "./rotationIdentity";
import {
  applyRotationViewport,
  DEFAULT_ROTATION_VIEWPORT,
} from "./rotationViewport";
import type { RotationViewport } from "./rotationViewport";
import { useElementSize } from "./useElementSize";
import { useRotationPan } from "./useRotationPan";

interface RotationChartProps {
  ariaLabel?: string;
  current: VisualRotationPoint[];
  trails: RotationTrail[];
  selectedCode: string;
  dimmedCodes: Set<string>;
  progress: number;
  onSelect: (code: string) => void;
  onClear: () => void;
  history: RotationPoint[];
  focusedCode?: string;
  showPointDetails?: boolean;
  viewport?: RotationViewport;
  onViewportChange?: (viewport: RotationViewport) => void;
}

function trailPath(points: VisualRotationPoint[], viewport: RotationViewport) {
  return points
    .map((point, index) => {
      const coordinate = applyRotationViewport(projectVisualPoint(point), viewport);
      return `${index === 0 ? "M" : "L"}${coordinate.x.toFixed(4)},${(100 - coordinate.y).toFixed(4)}`;
    })
    .join(" ");
}

export const RotationChart = memo(function RotationChart({
  ariaLabel = "行业相对轮动四象限",
  current,
  trails,
  selectedCode,
  dimmedCodes,
  progress,
  onSelect,
  onClear,
  history,
  focusedCode = "",
  showPointDetails = false,
  viewport = DEFAULT_ROTATION_VIEWPORT,
  onViewportChange,
}: RotationChartProps) {
  const panHandlers = useRotationPan(viewport, onViewportChange, onClear);
  const plotSize = useElementSize();
  const labelPlacements = useMemo(() => layoutRotationLabels(current.map((point) => {
    const coordinate = applyRotationViewport(projectVisualPoint(point), viewport);
    const selected = point.industry_code === selectedCode;
    const emphasized = selected || point.industry_code === focusedCode;
    return {
      code: point.industry_code,
      name: point.industry_name,
      nodeX: coordinate.x / 100 * plotSize.width,
      nodeY: (100 - coordinate.y) / 100 * plotSize.height,
      selected,
      emphasized,
      detailed: showPointDetails && emphasized,
    };
  }), plotSize.width, plotSize.height), [
    current,
    focusedCode,
    plotSize.height,
    plotSize.width,
    selectedCode,
    showPointDetails,
    viewport,
  ]);
  const labelsByCode = useMemo(
    () => new Map(labelPlacements.map((placement) => [placement.code, placement])),
    [labelPlacements],
  );

  return (
    <section
      aria-label={ariaLabel}
      className={[
        "rotation-plot",
        current.length > 30 ? "rotation-plot--dense-labels" : "",
        onViewportChange ? "rotation-plot--pannable" : "",
      ].join(" ")}
      data-animation-progress={progress.toFixed(3)}
      data-label-count={labelPlacements.length}
      data-label-rail-count={labelPlacements.filter((placement) => placement.rail).length}
      data-trail-count={trails.length}
      data-zoom={viewport.zoom.toFixed(2)}
      ref={plotSize.ref}
      {...panHandlers}
    >
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
      <div className="plot-safe-frame" aria-hidden="true">
        <small>安全绘图区</small>
      </div>
      <span className="axis-label axis-label--x">相对趋势 →</span>
      <span className="axis-label axis-label--y">相对动量 →</span>
      <svg
        className="rotation-trail"
        preserveAspectRatio="none"
        viewBox="0 0 100 100"
        aria-hidden="true"
      >
        {trails.map((trail) => (
          <path
            className={trail.selected ? "is-selected" : ""}
            d={trailPath(trail.points, viewport)}
            key={trail.industryCode}
            data-motion={trail.motionState}
            style={{ stroke: trail.color }}
          />
        ))}
      </svg>
      <RotationLabelLeaders
        height={plotSize.height}
        placements={labelPlacements}
        width={plotSize.width}
      />
      {current.map((point) => {
        const pointHistory = history.filter((item) =>
          item.industry_code === point.industry_code
          && item.trade_date <= point.trade_date);
        const state = motionState(pointHistory);
        return <RotationNode
          dimmed={dimmedCodes.has(point.industry_code)}
          focusedCode={focusedCode}
          history={pointHistory}
          key={point.industry_code}
          labelPlacement={labelsByCode.get(point.industry_code)}
          onSelect={onSelect}
          point={point}
          selectedCode={selectedCode}
          showPointDetails={showPointDetails}
          state={state}
          viewport={viewport}
        />;
      })}
    </section>
  );
});
