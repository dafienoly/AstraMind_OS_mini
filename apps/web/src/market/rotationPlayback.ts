import type { RotationPoint, VisualRotationPoint } from "./rotationTypes";
import { visualPointFromContract } from "./rotationProjection";

export function easeInOut(progress: number) {
  const bounded = Math.max(0, Math.min(1, progress));
  return bounded * bounded * (3 - 2 * bounded);
}

export function interpolateRotationPoints(
  current: RotationPoint[],
  next: RotationPoint[],
  progress: number,
): VisualRotationPoint[] {
  const eased = easeInOut(progress);
  const nextByCode = new Map(next.map((point) => [point.industry_code, point]));
  return current.map((point) => {
    const destination = nextByCode.get(point.industry_code) ?? point;
    const startVisual = visualPointFromContract(point);
    const endVisual = visualPointFromContract(destination);
    return {
      ...point,
      display_trend:
        startVisual.display_trend
        + (endVisual.display_trend - startVisual.display_trend) * eased,
      display_momentum:
        startVisual.display_momentum
        + (endVisual.display_momentum - startVisual.display_momentum) * eased,
    };
  });
}

export function visualPoint(point: RotationPoint): VisualRotationPoint {
  return visualPointFromContract(point);
}

export function continuousPlaybackFrame(
  elapsedMs: number,
  durationSeconds: number,
  originIndex: number,
  lastIndex: number,
) {
  const globalProgress = Math.min(1, Math.max(0, elapsedMs / (durationSeconds * 1000)));
  const exactIndex = originIndex + globalProgress * (lastIndex - originIndex);
  const dateIndex = Math.min(lastIndex, Math.floor(exactIndex));
  return {
    dateIndex,
    withinDay: dateIndex === lastIndex ? 0 : exactIndex - dateIndex,
    done: globalProgress >= 1,
  };
}
