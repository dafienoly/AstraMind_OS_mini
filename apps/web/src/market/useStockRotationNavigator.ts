import { useEffect, useMemo, useState } from "react";
import type { KeyboardEvent } from "react";

import { visualPoint } from "./rotationPlayback";
import { projectVisualPoint } from "./rotationProjection";
import {
  buildRotationScreenRows,
  recentRotationEventCodes,
} from "./rotationScreening";
import type { IndustryHierarchyView } from "./rotationTypes";
import {
  DEFAULT_ROTATION_VIEWPORT,
  fitRotationViewport,
  zoomRotationViewport,
} from "./rotationViewport";
import { useHierarchyScreening } from "./useHierarchyScreening";

export function useStockRotationNavigator(
  view: IndustryHierarchyView,
  selected: string,
  onInstrument: (code: string) => void,
) {
  const screening = useHierarchyScreening("stock_");
  const currentDate = view.rotation?.dates.at(-1);
  const current = useMemo(
    () => view.rotation?.points.filter((point) => point.trade_date === currentDate) ?? [],
    [view.rotation, currentDate],
  );
  const eventCodes = useMemo(
    () => recentRotationEventCodes(view.rotation, currentDate ?? ""),
    [view.rotation, currentDate],
  );
  const rows = useMemo(() => buildRotationScreenRows({
    identities: view.nodes,
    current,
    history: view.rotation?.points ?? [],
    options: screening,
  }).filter((row) => !screening.recentOnly || eventCodes.has(row.code)),
  [view.nodes, view.rotation, current, screening, eventCodes]);
  const visibleCodes = useMemo(() => new Set(rows.map((row) => row.code)), [rows]);
  const plotCoordinates = useMemo(
    () => current.map((point) => projectVisualPoint(visualPoint(point))),
    [current],
  );
  const [expanded, setExpanded] = useState(false);
  const [trailLength, setTrailLength] = useState(view.nodes.length > 8 ? 5 : 10);
  const [viewport, setViewport] = useState(DEFAULT_ROTATION_VIEWPORT);
  const [focusedCode, setFocusedCode] = useState(selected);
  useEffect(() => setFocusedCode(selected), [selected]);

  function collapse() {
    setExpanded(false);
    setViewport(DEFAULT_ROTATION_VIEWPORT);
  }

  function onKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key === "Escape") return collapse();
    if (event.target !== event.currentTarget) return;
    if (event.key === "Enter" && focusedCode) return onInstrument(focusedCode);
    if (event.key !== "ArrowDown" && event.key !== "ArrowUp") return;
    event.preventDefault();
    const codes = rows.map((row) => row.code);
    if (!codes.length) return;
    const currentIndex = Math.max(0, codes.indexOf(focusedCode || selected));
    const change = event.key === "ArrowDown" ? 1 : -1;
    setFocusedCode(codes[(currentIndex + change + codes.length) % codes.length]);
  }

  return {
    screening,
    rows,
    visibleCodes,
    selectionFiltered: Boolean(selected && !visibleCodes.has(selected)),
    expanded,
    setExpanded,
    trailLength,
    setTrailLength,
    viewport,
    setViewport,
    focusedCode,
    setFocusedCode,
    collapse,
    onKeyDown,
    fit: () => setViewport(fitRotationViewport(plotCoordinates)),
    zoom: (change: number) => setViewport((currentViewport) =>
      zoomRotationViewport(currentViewport, change)),
  };
}
