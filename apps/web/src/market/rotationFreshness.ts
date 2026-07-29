import type { RotationSnapshot } from "./rotationTypes";

export type RotationFreshness =
  | { kind: "current"; latestDate: string }
  | { kind: "stale"; latestDate: string; expectedDate: string }
  | { kind: "blocked"; latestDate: string; reason: string };

const EXPECTED_DATE = /^expected_completed_trade_date[:=](\d{4}-\d{2}-\d{2})$/;
const BLOCKED = /^rotation_blocked:(.+)$/;

export function assessRotationFreshness(
  snapshot: RotationSnapshot,
): RotationFreshness {
  const latestDate = snapshot.date_range[1];
  for (const gap of snapshot.known_gaps) {
    const blocked = BLOCKED.exec(gap);
    if (blocked) {
      return { kind: "blocked", latestDate, reason: blocked[1] };
    }
  }
  for (const gap of snapshot.known_gaps) {
    const expected = EXPECTED_DATE.exec(gap)?.[1];
    if (expected && latestDate < expected) {
      return { kind: "stale", latestDate, expectedDate: expected };
    }
  }
  return { kind: "current", latestDate };
}
