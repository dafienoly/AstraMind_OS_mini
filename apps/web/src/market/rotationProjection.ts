import type { RotationPoint, VisualRotationPoint } from "./rotationTypes";

export const DISPLAY_TRANSFORM_VERSION = "rotation-display-tanh-v1.0.0";

export interface PlotCoordinate {
  x: number;
  y: number;
}

const LEGACY_MIN = 85;
const LEGACY_SPAN = 30;
export const PLOT_SAFE_X = 5;
export const PLOT_SAFE_Y = 8;

export function displayValue(rawZ: number): number {
  return 100 + 14 * Math.tanh(rawZ / 2.5);
}

export function visualPointFromContract(point: RotationPoint): VisualRotationPoint {
  const usesTanh = point.display_transform_version === DISPLAY_TRANSFORM_VERSION;
  if (usesTanh && (point.raw_z_trend == null || point.raw_z_momentum == null)) {
    throw new Error("轮动快照声明 tanh 显示变换但缺少 raw_z");
  }
  return {
    ...point,
    display_trend: usesTanh ? displayValue(point.raw_z_trend!) : point.relative_trend,
    display_momentum: usesTanh
      ? displayValue(point.raw_z_momentum!)
      : point.relative_momentum,
  };
}

export function projectVisualPoint(point: VisualRotationPoint): PlotCoordinate {
  return {
    x: padded((point.display_trend - LEGACY_MIN) / LEGACY_SPAN, PLOT_SAFE_X),
    y: padded((point.display_momentum - LEGACY_MIN) / LEGACY_SPAN, PLOT_SAFE_Y),
  };
}

function clamp(value: number): number {
  return Math.max(0, Math.min(1, value));
}

function padded(value: number, paddingPercent: number): number {
  return paddingPercent + clamp(value) * (100 - paddingPercent * 2);
}
