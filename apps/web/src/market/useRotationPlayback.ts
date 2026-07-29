import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  continuousPlaybackFrame,
  interpolateRotationPoints,
} from "./rotationPlayback";
import type {
  ContinuousDuration,
  PlaybackMode,
  RotationPoint,
  RotationSpeed,
  RotationSnapshot,
} from "./rotationTypes";

const FRAME_DURATION_MS = 900;

function usePrefersReducedMotion() {
  const [reduced, setReduced] = useState(
    () => window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false,
  );

  useEffect(() => {
    const query = window.matchMedia?.("(prefers-reduced-motion: reduce)");
    if (!query) return;
    const update = () => setReduced(query.matches);
    query.addEventListener("change", update);
    return () => query.removeEventListener("change", update);
  }, []);

  return reduced;
}

export function useRotationPlayback({
  snapshot,
  dateIndex,
  setDateIndex,
  playing,
  setPlaying,
  speed,
  mode,
  continuousDuration,
}: {
  snapshot: RotationSnapshot | null;
  dateIndex: number;
  setDateIndex: (index: number) => void;
  playing: boolean;
  setPlaying: (value: boolean) => void;
  speed: RotationSpeed;
  mode: PlaybackMode;
  continuousDuration: ContinuousDuration;
}) {
  const [progress, setProgress] = useState(0);
  const progressRef = useRef(0);
  const reducedMotion = usePrefersReducedMotion();
  const dateIndexRef = useRef(dateIndex);
  useEffect(() => {
    dateIndexRef.current = dateIndex;
  }, [dateIndex]);

  const resetProgress = useCallback(() => {
    progressRef.current = 0;
    setProgress(0);
  }, []);

  const goToDate = useCallback((index: number) => {
    setPlaying(false);
    resetProgress();
    setDateIndex(index);
  }, [resetProgress, setDateIndex, setPlaying]);

  useDailyPlayback({
    dateIndex, mode, playing, progressRef, reducedMotion, resetProgress,
    setDateIndex, setPlaying, setProgress, snapshot, speed,
  });
  useContinuousPlayback({
    continuousDuration, dateIndex, dateIndexRef, mode, playing, progressRef,
    reducedMotion, resetProgress, setDateIndex, setPlaying, setProgress, snapshot,
  });

  const visualCurrent = useMemo(() => {
    if (!snapshot || dateIndex < 0) return [];
    const currentDate = snapshot.dates[dateIndex];
    const nextDate = snapshot.dates[dateIndex + 1];
    const current = pointsOn(snapshot.points, currentDate);
    const next = nextDate ? pointsOn(snapshot.points, nextDate) : current;
    return interpolateRotationPoints(current, next, progress);
  }, [dateIndex, progress, snapshot]);

  return {
    goToDate,
    progress,
    reducedMotion,
    resetProgress,
    visualCurrent,
  };
}

interface EffectOptions {
  snapshot: RotationSnapshot | null;
  dateIndex: number;
  setDateIndex: (index: number) => void;
  playing: boolean;
  setPlaying: (value: boolean) => void;
  mode: PlaybackMode;
  reducedMotion: boolean;
  progressRef: { current: number };
  resetProgress: () => void;
  setProgress: (value: number) => void;
}

function useDailyPlayback(options: EffectOptions & { speed: RotationSpeed }) {
  const {
    dateIndex, mode, playing, progressRef, reducedMotion, resetProgress,
    setDateIndex, setPlaying, setProgress, snapshot, speed,
  } = options;
  useEffect(() => {
    if (mode !== "daily" || !playing || !snapshot || dateIndex < 0) return;
    if (dateIndex >= snapshot.dates.length - 1) {
      setPlaying(false);
      resetProgress();
      return;
    }
    const duration = FRAME_DURATION_MS / speed;
    if (reducedMotion) {
      const timer = window.setTimeout(() => {
        resetProgress();
        setDateIndex(dateIndex + 1);
      }, duration);
      return () => window.clearTimeout(timer);
    }
    let animationFrame = 0;
    let startedAt: number | undefined;
    const initialProgress = progressRef.current;
    const tick = (timestamp: number) => {
      startedAt ??= timestamp;
      const next = Math.min(1, initialProgress + (timestamp - startedAt) / duration);
      progressRef.current = next;
      setProgress(next);
      if (next >= 1) {
        resetProgress();
        setDateIndex(dateIndex + 1);
        return;
      }
      animationFrame = window.requestAnimationFrame(tick);
    };
    animationFrame = window.requestAnimationFrame(tick);
    return () => window.cancelAnimationFrame(animationFrame);
  }, [
    dateIndex, mode, playing, progressRef, reducedMotion, resetProgress,
    setDateIndex, setPlaying, setProgress, snapshot, speed,
  ]);
}

function useContinuousPlayback(
  options: EffectOptions & {
    continuousDuration: ContinuousDuration;
    dateIndexRef: { current: number };
  },
) {
  const {
    continuousDuration, dateIndex, dateIndexRef, mode, playing, progressRef,
    reducedMotion, resetProgress, setDateIndex, setPlaying, setProgress, snapshot,
  } = options;
  useEffect(() => {
    if (mode !== "continuous" || !playing || !snapshot || dateIndex < 0) return;
    if (reducedMotion) {
      setPlaying(false);
      return;
    }
    const lastIndex = snapshot.dates.length - 1;
    const origin = dateIndex;
    if (lastIndex <= origin) {
      setPlaying(false);
      return;
    }
    let animationFrame = 0;
    let startedAt: number | undefined;
    const tick = (timestamp: number) => {
      startedAt ??= timestamp;
      const frame = continuousPlaybackFrame(
        timestamp - startedAt, continuousDuration, origin, lastIndex,
      );
      if (frame.dateIndex !== dateIndexRef.current) {
        dateIndexRef.current = frame.dateIndex;
        setDateIndex(frame.dateIndex);
      }
      progressRef.current = frame.withinDay;
      setProgress(frame.withinDay);
      if (frame.done) {
        setPlaying(false);
        resetProgress();
        return;
      }
      animationFrame = window.requestAnimationFrame(tick);
    };
    animationFrame = window.requestAnimationFrame(tick);
    return () => window.cancelAnimationFrame(animationFrame);
  }, [
    continuousDuration, dateIndex < 0, dateIndexRef, mode, playing, progressRef,
    reducedMotion, resetProgress, setDateIndex, setPlaying, setProgress, snapshot,
  ]);
}

function pointsOn(points: RotationPoint[], date: string | undefined) {
  if (!date) return [];
  return points.filter((point) => point.trade_date === date);
}
