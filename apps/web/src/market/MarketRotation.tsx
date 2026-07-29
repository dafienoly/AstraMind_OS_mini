import { useCallback, useEffect, useMemo, useState } from "react";
import type { Dispatch, SetStateAction } from "react";

import { RotationStatus } from "./RotationPanels";
import { RotationReadyView } from "./RotationReadyView";
import type {
  RotationSortKey,
  RotationSortOrder,
} from "./rotationScreening";
import {
  loadRotationSnapshot,
  readRotationInitialParams,
  type RotationInitialParams,
  type RotationLoadState,
} from "./rotationSnapshotClient";
import type {
  MotionState,
  Quadrant,
  ContinuousDuration,
  PlaybackMode,
  RotationSnapshot,
  RotationSpeed,
  TrailMode,
} from "./rotationTypes";
import { useRotationDerived, useRotationUrl } from "./useRotationDerived";
import { useRotationPlayback } from "./useRotationPlayback";

export function MarketRotation() {
  const initial = useMemo(readRotationInitialParams, []);
  const [load, setLoad] = useState<RotationLoadState>({ kind: "loading" });
  const [refreshing, setRefreshing] = useState(false);
  useEffect(() => {
    let active = true;
    loadRotationSnapshot().then((result) => {
      if (active) setLoad(result);
    });
    return () => {
      active = false;
    };
  }, []);
  const refresh = useCallback(async () => {
    setRefreshing(true);
    try {
      setLoad(await loadRotationSnapshot());
    } finally {
      setRefreshing(false);
    }
  }, []);
  if (load.kind !== "ready") return <RotationStatus state={load} />;
  return <LoadedRotation
    initial={initial}
    onRefresh={refresh}
    refreshing={refreshing}
    snapshot={load.snapshot}
  />;
}

function LoadedRotation({
  initial,
  onRefresh,
  refreshing,
  snapshot,
}: {
  initial: RotationInitialParams;
  onRefresh: () => void;
  refreshing: boolean;
  snapshot: RotationSnapshot;
}) {
  const requested = initial.date ? snapshot.dates.indexOf(initial.date) : -1;
  const [dateIndex, setDateIndex] = useState(
    requested >= 0 ? requested : snapshot.dates.length - 1,
  );
  const [selected, setSelected] = useState(
    initial.selected,
  );
  const [trail, setTrail] = useState(initial.trail);
  const [trailMode, setTrailMode] = useState<TrailMode>(initial.trailMode);
  const [quadrant, setQuadrant] = useState<Quadrant | "">(initial.quadrant);
  const [motion, setMotion] = useState<MotionState | "">(initial.motion);
  const [sort, setSort] = useState<RotationSortKey>(initial.sort);
  const [order, setOrder] = useState<RotationSortOrder>(initial.order);
  const [recentOnly, setRecentOnly] = useState(initial.recentOnly);
  const [onlySelected, setOnlySelected] = useState(false);
  const [search, setSearch] = useState(initial.search);
  const [speed, setSpeed] = useState<RotationSpeed>(1);
  const [playing, setPlaying] = useState(false);
  const [playbackMode, setPlaybackMode] = useState<PlaybackMode>("daily");
  const [continuousDuration, setContinuousDuration] =
    useState<ContinuousDuration>(20);
  const [formulaOpen, setFormulaOpen] = useState(false);
  const [hierarchyParent, setHierarchyParent] = useState("");
  const playback = useRotationPlayback({
    snapshot,
    dateIndex,
    setDateIndex,
    playing,
    setPlaying,
    speed,
    mode: playbackMode,
    continuousDuration,
  });
  const derived = useRotationDerived({
    snapshot, dateIndex, trail, trailMode, selected, search, quadrant,
    motion, sort, order, recentOnly, onlySelected,
    visualCurrent: playback.visualCurrent,
  });
  useRotationUrl({
    currentDate: derived.currentDate, dateIndex, trail, trailMode, selected,
    search, quadrant, motion, sort, order, recentOnly,
  });
  const { stop, select, togglePlaying } = useRotationInteractions({
    playing, playbackMode, setPlaying, setSelected,
    resetProgress: playback.resetProgress, goToDate: playback.goToDate,
  });
  return (
    <RotationReadyView
      {...derived}
      dateIndex={dateIndex}
      formulaOpen={formulaOpen}
      goToDate={playback.goToDate}
      onFormulaToggle={() => setFormulaOpen((value) => !value)}
      onOnlySelected={stopped(stop, setOnlySelected)}
      onQuadrant={stopped(stop, setQuadrant)}
      onMotion={stopped(stop, setMotion)}
      onSort={stopped(stop, setSort)}
      onOrder={stopped(stop, setOrder)}
      onScreenReset={() => {
        stop();
        setSearch("");
        setQuadrant("");
        setMotion("");
        setSort("name");
        setOrder("asc");
      }}
      onRecentOnly={stopped(stop, setRecentOnly)}
      onRefresh={onRefresh}
      onSearch={stopped(stop, setSearch)}
      onSelect={select}
      onTrailMode={stopped(stop, setTrailMode)}
      onlySelected={onlySelected}
      playing={playing}
      progress={playback.progress}
      quadrant={quadrant}
      motion={motion}
      sort={sort}
      order={order}
      recentOnly={recentOnly}
      reducedMotion={playback.reducedMotion}
      refreshing={refreshing}
      search={search}
      selected={selected}
      onPlayToggle={togglePlaying}
      playbackMode={playbackMode}
      onPlaybackMode={stopped(stop, setPlaybackMode)}
      continuousDuration={continuousDuration}
      onContinuousDuration={setContinuousDuration}
      hierarchyParent={hierarchyParent}
      onHierarchyParent={setHierarchyParent}
      setSpeed={setSpeed}
      setTrail={stopped(stop, setTrail)}
      snapshot={snapshot}
      speed={speed}
      trail={trail}
      trailMode={trailMode}
    />
  );
}

function useRotationInteractions(options: {
  playing: boolean;
  playbackMode: PlaybackMode;
  setPlaying: (value: boolean) => void;
  setSelected: Dispatch<SetStateAction<string>>;
  resetProgress: () => void;
  goToDate: (index: number) => void;
}) {
  const stop = () => {
    options.setPlaying(false);
    options.resetProgress();
  };
  useEffect(() => {
    const clear = (event: KeyboardEvent) => {
      if (event.key === "Escape") options.setSelected("");
    };
    window.addEventListener("keydown", clear);
    return () => window.removeEventListener("keydown", clear);
  }, [options.setSelected]);
  const select = (code: string) => {
    stop();
    options.setSelected((current) => current === code ? "" : code);
  };
  const togglePlaying = () => {
    if (options.playing) return options.setPlaying(false);
    if (options.playbackMode === "continuous") options.goToDate(0);
    options.setPlaying(true);
  };
  return { stop, select, togglePlaying };
}

function stopped<T>(stop: () => void, setter: (value: T) => void) {
  return (value: T) => {
    stop();
    setter(value);
  };
}
