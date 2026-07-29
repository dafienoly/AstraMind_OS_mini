import type { RotationPoint, VisualRotationPoint } from "./rotationTypes";
import { quadrantLabels } from "./rotationTypes";
import type { RotationLabelPlacement } from "./rotationLabelLayout";
import { projectVisualPoint } from "./rotationProjection";
import { industryColor, motionLabels, motionMetrics } from "./rotationIdentity";
import { applyRotationViewport } from "./rotationViewport";
import type { RotationViewport } from "./rotationViewport";

export function RotationNode({
  point,
  history,
  selectedCode,
  focusedCode,
  dimmed,
  state,
  showPointDetails,
  viewport,
  onSelect,
  labelPlacement,
}: {
  point: VisualRotationPoint;
  history: RotationPoint[];
  selectedCode: string;
  focusedCode: string;
  dimmed: boolean;
  state: ReturnType<typeof motionMetrics>["state"];
  showPointDetails: boolean;
  viewport: RotationViewport;
  onSelect: (code: string) => void;
  labelPlacement?: RotationLabelPlacement;
}) {
  const coordinate = applyRotationViewport(projectVisualPoint(point), viewport);
  const metrics = motionMetrics(history);
  const emphasized = point.industry_code === selectedCode
    || point.industry_code === focusedCode;
  const labelStyle = labelPlacement ? {
    boxSizing: "border-box" as const,
    width: `${labelPlacement.width}px`,
    height: `${labelPlacement.height}px`,
    left: "50%",
    top: "50%",
    transform: `translate(${labelPlacement.labelX - labelPlacement.nodeX}px, ${labelPlacement.labelY - labelPlacement.nodeY}px)`,
  } : undefined;
  const classes = [
    `rotation-node rotation-node--${point.quadrant}`,
    point.industry_code === selectedCode ? "is-selected" : "",
    point.industry_code === focusedCode ? "is-keyboard-focused" : "",
    dimmed ? "is-dimmed" : "",
    point.display_trend >= 110 ? "is-edge-right" : "",
    point.display_trend <= 90 ? "is-edge-left" : "",
    point.display_momentum >= 110 ? "is-edge-top" : "",
    point.display_momentum <= 90 ? "is-edge-bottom" : "",
    point.overflow ? "has-overflow" : "",
    `is-motion-${state}`,
  ].join(" ");
  return <button
    aria-label={`${point.industry_name}，${point.trade_date}，相对趋势 ${point.relative_trend.toFixed(2)}，相对动量 ${point.relative_momentum.toFixed(2)}，${quadrantLabels[point.quadrant]}，${motionLabels[state]}${point.overflow ? "，坐标已截断" : ""}`}
    className={classes}
    onClick={(event) => {
      event.stopPropagation();
      onSelect(point.industry_code);
    }}
    style={{ left: `${coordinate.x}%`, bottom: `${coordinate.y}%`, color: industryColor(point.industry_code) }}
    type="button"
  >
    <i aria-hidden="true" />
    <span className={labelPlacement?.rail ? "is-rail-label" : ""} style={labelStyle}>
      <b>
        {point.industry_name}
        {emphasized ? ` · ${motionLabels[state]}${point.overflow ? " · 截断" : ""}` : ""}
      </b>
      {showPointDetails && emphasized ? <small>
        X {point.relative_trend.toFixed(2)} · Y {point.relative_momentum.toFixed(2)}
        {" · "}速度 {metrics.speed?.toFixed(2) ?? "—"}
      </small> : null}
    </span>
  </button>;
}
