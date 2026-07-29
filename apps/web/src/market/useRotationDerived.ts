import { useEffect, useMemo } from "react";

import { buildRotationTrails } from "./rotationTrails";
import {
  buildRotationScreenRows,
  type RotationSortKey,
  type RotationSortOrder,
} from "./rotationScreening";
import type {
  MotionState,
  Quadrant,
  RotationPoint,
  RotationSnapshot,
  TrailMode,
  VisualRotationPoint,
} from "./rotationTypes";
import { quadrantLabels } from "./rotationTypes";

export function useRotationDerived(options: {
  snapshot: RotationSnapshot;
  dateIndex: number;
  trail: number;
  trailMode: TrailMode;
  selected: string;
  search: string;
  quadrant: Quadrant | "";
  motion: MotionState | "";
  sort: RotationSortKey;
  order: RotationSortOrder;
  recentOnly: boolean;
  onlySelected: boolean;
  visualCurrent: VisualRotationPoint[];
}) {
  const {
    snapshot, dateIndex, trail, trailMode, selected, search, quadrant, motion,
    sort, order,
    recentOnly, onlySelected, visualCurrent,
  } = options;
  const currentDate = snapshot.dates[dateIndex] ?? "";
  const current = useMemo(
    () => snapshot.points.filter((point) => point.trade_date === currentDate),
    [snapshot, currentDate],
  );
  const recentCodes = useMemo(
    () => recentEventCodes(snapshot, dateIndex, currentDate),
    [snapshot, dateIndex, currentDate],
  );
  const screenRows = useMemo(() => buildRotationScreenRows({
    identities: current.map((point) => ({
      code: point.industry_code,
      name: point.industry_name,
    })),
    current,
    history: snapshot.points,
    options: { search, quadrant, motion, sort, order },
  }).filter((row) =>
    (!recentOnly || recentCodes.has(row.code))
    && (!onlySelected || row.code === selected)),
    [
      current, snapshot.points, search, quadrant, motion, sort, order,
      recentOnly, recentCodes, onlySelected, selected,
    ],
  );
  const visibleCodes = useMemo(
    () => new Set(screenRows.map((row) => row.code)),
    [screenRows],
  );
  const dimmed = useMemo(
    () => new Set(current
      .filter((point) => !visibleCodes.has(point.industry_code))
      .map((point) => point.industry_code)),
    [current, visibleCodes],
  );
  const trails = useMemo(
    () => buildRotationTrails({
      snapshot, dateIndex, length: trail, mode: trailMode,
      selectedCode: selected, visibleCodes, visualCurrent,
    }),
    [
      snapshot, dateIndex, trail, trailMode, selected, visibleCodes,
      visualCurrent,
    ],
  );
  return {
    currentDate, current, dimmed, trails, visualCurrent, screenRows,
    counts: quadrantCounts(current),
  };
}

export function useRotationUrl(options: {
  currentDate: string;
  dateIndex: number;
  trail: number;
  trailMode: TrailMode;
  selected: string;
  search: string;
  quadrant: Quadrant | "";
  motion: MotionState | "";
  sort: RotationSortKey;
  order: RotationSortOrder;
  recentOnly: boolean;
}) {
  const {
    currentDate, dateIndex, trail, trailMode, selected, search, quadrant,
    motion, sort, order, recentOnly,
  } = options;
  useEffect(() => {
    if (dateIndex < 0) return;
    const params = new URLSearchParams({
      tab: "industries", view: "rotation", as_of: currentDate,
      trail: String(trail), trail_mode: trailMode,
    });
    if (selected) params.set("industry", selected);
    if (search) params.set("search", search);
    if (quadrant) params.set("quadrant", quadrant);
    if (motion) params.set("motion", motion);
    if (sort !== "name") params.set("sort", sort);
    if (order !== "asc") params.set("order", order);
    if (recentOnly) params.set("events", "recent");
    window.history.replaceState(null, "", `/market?${params}`);
  }, [
    currentDate, dateIndex, trail, trailMode, selected, search, quadrant,
    motion, sort, order, recentOnly,
  ]);
}

function recentEventCodes(
  snapshot: RotationSnapshot,
  dateIndex: number,
  currentDate: string,
) {
  const start = snapshot.dates[Math.max(0, dateIndex - 4)];
  return new Set(snapshot.events
    .filter((event) =>
      event.confirmed_date >= start && event.confirmed_date <= currentDate)
    .map((event) => event.industry_code));
}

function quadrantCounts(current: RotationPoint[]) {
  return Object.fromEntries(Object.keys(quadrantLabels).map((key) => [
    key,
    current.filter((point) => point.quadrant === key).length,
  ]));
}
