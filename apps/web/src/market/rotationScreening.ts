import { motionMetrics } from "./rotationIdentity";
import type {
  IndustryHierarchyNode,
  MotionState,
  Quadrant,
  RotationPoint,
  RotationSnapshot,
} from "./rotationTypes";

export type RotationSortKey = "name" | "trend" | "momentum" | "speed" | "distance";
export type RotationSortOrder = "asc" | "desc";

export interface RotationScreenOptions {
  search: string;
  quadrant: Quadrant | "";
  motion: MotionState | "";
  sort: RotationSortKey;
  order: RotationSortOrder;
}

export interface RotationScreenRow {
  code: string;
  name: string;
  point: RotationPoint | null;
  motion: MotionState;
  speed: number | null;
  acceleration: number | null;
  distance: number | null;
}

export function buildRotationScreenRows({
  identities,
  current,
  history,
  options,
}: {
  identities: Pick<IndustryHierarchyNode, "code" | "name">[];
  current: RotationPoint[];
  history: RotationPoint[];
  options: RotationScreenOptions;
}): RotationScreenRow[] {
  const currentByCode = new Map(current.map((point) => [point.industry_code, point]));
  const currentDate = current[0]?.trade_date ?? "";
  const historyByCode = groupHistory(history, currentDate);
  const query = options.search.trim().toLocaleLowerCase();
  const rows = identities.flatMap((identity) => {
    const point = currentByCode.get(identity.code) ?? null;
    const metrics = motionMetrics(historyByCode.get(identity.code) ?? []);
    const row: RotationScreenRow = {
      code: identity.code,
      name: identity.name,
      point,
      motion: metrics.state,
      speed: metrics.speed,
      acceleration: metrics.acceleration,
      distance: point
        ? Math.hypot(point.relative_trend - 100, point.relative_momentum - 100)
        : null,
    };
    if (query && !`${identity.name} ${identity.code}`.toLocaleLowerCase().includes(query)) {
      return [];
    }
    if (options.quadrant && point?.quadrant !== options.quadrant) return [];
    if (options.motion && metrics.state !== options.motion) return [];
    return [row];
  });
  return rows.sort((left, right) => compareRows(left, right, options));
}

export function recentRotationEventCodes(
  snapshot: RotationSnapshot | null,
  currentDate: string,
) {
  if (!snapshot) return new Set<string>();
  const dateIndex = snapshot.dates.indexOf(currentDate);
  const start = snapshot.dates[Math.max(0, dateIndex - 4)] ?? currentDate;
  return new Set(snapshot.events
    .filter((event) =>
      event.confirmed_date >= start && event.confirmed_date <= currentDate)
    .map((event) => event.industry_code));
}

function groupHistory(history: RotationPoint[], currentDate: string) {
  const grouped = new Map<string, RotationPoint[]>();
  for (const point of history) {
    if (currentDate && point.trade_date > currentDate) continue;
    const points = grouped.get(point.industry_code) ?? [];
    points.push(point);
    grouped.set(point.industry_code, points);
  }
  for (const points of grouped.values()) {
    points.sort((left, right) => left.trade_date.localeCompare(right.trade_date));
  }
  return grouped;
}

function compareRows(
  left: RotationScreenRow,
  right: RotationScreenRow,
  options: Pick<RotationScreenOptions, "sort" | "order">,
) {
  const direction = options.order === "asc" ? 1 : -1;
  if (options.sort === "name") {
    const compared = left.name.localeCompare(right.name, "zh-CN");
    return compared === 0 ? left.code.localeCompare(right.code) : compared * direction;
  }
  const leftValue = numericValue(left, options.sort);
  const rightValue = numericValue(right, options.sort);
  if (leftValue === null || rightValue === null) {
    if (leftValue === rightValue) return left.code.localeCompare(right.code);
    return leftValue === null ? 1 : -1;
  }
  if (leftValue === rightValue) return left.code.localeCompare(right.code);
  return (leftValue - rightValue) * direction;
}

function numericValue(row: RotationScreenRow, sort: RotationSortKey) {
  if (sort === "trend") return row.point?.relative_trend ?? null;
  if (sort === "momentum") return row.point?.relative_momentum ?? null;
  if (sort === "speed") return row.speed;
  return row.distance;
}
