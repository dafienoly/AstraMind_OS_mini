import type { RealtimeMarketProjection } from "../market-dashboard/types";
import type { RotationPoint, RotationSnapshot, VisualRotationPoint } from "./rotationTypes";
import { visualPointFromContract } from "./rotationProjection";

export type RotationIntradayPoint = {
  industry_code: string;
  anchor: VisualRotationPoint;
  endpoint: VisualRotationPoint;
};

export function buildRotationIntraday(
  snapshot: RotationSnapshot,
  realtime: RealtimeMarketProjection | null,
): RotationIntradayPoint[] {
  if (!realtime?.industries?.length) return [];
  const changes = realtime.industries.map((item) => item.change_percent);
  const mean = changes.reduce((sum, value) => sum + value, 0) / changes.length;
  const variance = changes.reduce((sum, value) => sum + (value - mean) ** 2, 0) / changes.length;
  const deviation = Math.sqrt(variance);
  const latestDate = snapshot.dates.at(-1);
  const anchors = new Map(
    snapshot.points
      .filter((point) => point.trade_date === latestDate)
      .map((point) => [point.industry_code, point]),
  );
  return realtime.industries.flatMap((live) => {
    const anchor = anchors.get(live.industry_code);
    if (!anchor || deviation === 0 || live.observed_constituents < 3) return [];
    const z = Math.max(-3, Math.min(3, (live.change_percent - mean) / deviation));
    const displayedAnchor = visual(anchor);
    const endpoint = {
      ...displayedAnchor,
      display_trend: displayedAnchor.display_trend + 0.6 * z,
      display_momentum: displayedAnchor.display_momentum + 1.2 * z,
    };
    return [{ industry_code: live.industry_code, anchor: displayedAnchor, endpoint }];
  });
}

function visual(point: RotationPoint): VisualRotationPoint {
  return visualPointFromContract(point);
}

export const ROTATION_INTRADAY_METHOD = "intraday-rotation-overlay-v1.0.0";
