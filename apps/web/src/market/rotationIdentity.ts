import type { MotionState, RotationPoint } from "./rotationTypes";

export const motionLabels: Record<MotionState, string> = {
  accelerating_up: "加速上升 ↑◎",
  decelerating_up: "减速上升 ↑⋯",
  accelerating_down: "加速下跌 ↓◎",
  decelerating_down: "减速下跌 ↓⋯",
  steady: "平稳 ·",
};

export const MOTION_DEFINITION_VERSION = "rotation-motion-v2.0.0";
export const MOTION_EPSILON = 0.01;

export interface MotionMetrics {
  state: MotionState;
  deltaMomentum: number | null;
  speed: number | null;
  acceleration: number | null;
}

export function industryColor(code: string): string {
  let hash = 2166136261;
  for (const character of code) {
    hash ^= character.charCodeAt(0);
    hash = Math.imul(hash, 16777619);
  }
  const hue = Math.abs(hash) % 360;
  return `hsl(${hue} 46% 40%)`;
}

export function motionMetrics(history: RotationPoint[]): MotionMetrics {
  if (history.length < 3) {
    return { state: "steady", deltaMomentum: null, speed: null, acceleration: null };
  }
  const [a, b, c] = history.slice(-3);
  const previousSpeed = Math.abs(b.relative_momentum - a.relative_momentum);
  const deltaMomentum = c.relative_momentum - b.relative_momentum;
  const speed = Math.abs(deltaMomentum);
  const acceleration = speed - previousSpeed;
  if (speed <= MOTION_EPSILON + Number.EPSILON * 100) {
    return { state: "steady", deltaMomentum, speed, acceleration };
  }
  const accelerating = acceleration > MOTION_EPSILON;
  const state = deltaMomentum > 0
    ? (accelerating ? "accelerating_up" : "decelerating_up")
    : (accelerating ? "accelerating_down" : "decelerating_down");
  return { state, deltaMomentum, speed, acceleration };
}

export function motionState(history: RotationPoint[]): MotionState {
  return motionMetrics(history).state;
}
