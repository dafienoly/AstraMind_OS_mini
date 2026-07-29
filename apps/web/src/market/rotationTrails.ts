import { visualPoint } from "./rotationPlayback";
import { industryColor, motionState } from "./rotationIdentity";
import type {
  RotationSnapshot,
  RotationTrail,
  TrailMode,
  VisualRotationPoint,
} from "./rotationTypes";

export function buildRotationTrails({
  snapshot,
  dateIndex,
  length,
  mode,
  selectedCode,
  visibleCodes,
  visualCurrent,
}: {
  snapshot: RotationSnapshot;
  dateIndex: number;
  length: number;
  mode: TrailMode;
  selectedCode: string;
  visibleCodes: Set<string>;
  visualCurrent: VisualRotationPoint[];
}): RotationTrail[] {
  const currentDate = snapshot.dates[dateIndex];
  const start = Math.max(0, dateIndex - length + 1);
  const dates = new Set(snapshot.dates.slice(start, dateIndex + 1));
  const current = snapshot.points.filter((point) => point.trade_date === currentDate);
  const codes = mode === "selected"
    ? new Set([selectedCode])
    : mode === "filtered"
      ? visibleCodes
      : new Set(current.map((point) => point.industry_code));
  const visualByCode = new Map(
    visualCurrent.map((point) => [point.industry_code, point]),
  );
  const grouped = new Map<string, VisualRotationPoint[]>();
  for (const point of snapshot.points) {
    if (!codes.has(point.industry_code) || !dates.has(point.trade_date)) continue;
    const points = grouped.get(point.industry_code) ?? [];
    points.push(
      point.trade_date === currentDate
        ? visualByCode.get(point.industry_code) ?? visualPoint(point)
        : visualPoint(point),
    );
    grouped.set(point.industry_code, points);
  }

  return current
    .filter((point) => codes.has(point.industry_code))
    .map((point) => ({
      industryCode: point.industry_code,
      industryName: point.industry_name,
      selected: point.industry_code === selectedCode,
      color: industryColor(point.industry_code),
      motionState: motionState(snapshot.points.filter((candidate) =>
        candidate.industry_code === point.industry_code
        && candidate.trade_date <= currentDate)),
      points: grouped.get(point.industry_code) ?? [],
    }));
}
