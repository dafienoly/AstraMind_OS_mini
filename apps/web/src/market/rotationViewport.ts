import type { PlotCoordinate } from "./rotationProjection";

export interface RotationViewport {
  centerX: number;
  centerY: number;
  zoom: number;
}

export const DEFAULT_ROTATION_VIEWPORT: RotationViewport = {
  centerX: 50,
  centerY: 50,
  zoom: 1,
};

export function applyRotationViewport(
  point: PlotCoordinate,
  viewport: RotationViewport,
): PlotCoordinate {
  return {
    x: 50 + (point.x - viewport.centerX) * viewport.zoom,
    y: 50 + (point.y - viewport.centerY) * viewport.zoom,
  };
}

export function zoomRotationViewport(
  viewport: RotationViewport,
  change: number,
): RotationViewport {
  return {
    ...viewport,
    zoom: Math.max(1, Math.min(3.2, viewport.zoom + change)),
  };
}

export function fitRotationViewport(points: PlotCoordinate[]): RotationViewport {
  if (!points.length) return DEFAULT_ROTATION_VIEWPORT;
  const xs = points.map((point) => point.x);
  const ys = points.map((point) => point.y);
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minY = Math.min(...ys);
  const maxY = Math.max(...ys);
  const spanX = Math.max(12, maxX - minX);
  const spanY = Math.max(12, maxY - minY);
  return {
    centerX: (minX + maxX) / 2,
    centerY: (minY + maxY) / 2,
    zoom: Math.max(1, Math.min(3.2, 76 / Math.max(spanX, spanY))),
  };
}

export function panRotationViewport(
  viewport: RotationViewport,
  deltaX: number,
  deltaY: number,
  width: number,
  height: number,
): RotationViewport {
  if (width <= 0 || height <= 0) return viewport;
  return {
    ...viewport,
    centerX: viewport.centerX - (deltaX / width) * (100 / viewport.zoom),
    centerY: viewport.centerY + (deltaY / height) * (100 / viewport.zoom),
  };
}
