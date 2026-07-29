import { useEffect, useMemo, useState } from "react";

import type {
  RotationScreenOptions,
  RotationSortKey,
  RotationSortOrder,
} from "./rotationScreening";
import type { MotionState, Quadrant } from "./rotationTypes";

const defaults: RotationScreenOptions = {
  search: "",
  quadrant: "",
  motion: "",
  sort: "name",
  order: "asc",
};

export function useHierarchyScreening(prefix: "l2_" | "stock_") {
  const initial = useMemo(() => readInitial(prefix), [prefix]);
  const [search, setSearch] = useState(initial.search);
  const [quadrant, setQuadrant] = useState<Quadrant | "">(initial.quadrant);
  const [motion, setMotion] = useState<MotionState | "">(initial.motion);
  const [sort, setSort] = useState<RotationSortKey>(initial.sort);
  const [order, setOrder] = useState<RotationSortOrder>(initial.order);
  const [recentOnly, setRecentOnly] = useState(initial.recentOnly);
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    setOrDelete(params, `${prefix}search`, search);
    setOrDelete(params, `${prefix}quadrant`, quadrant);
    setOrDelete(params, `${prefix}motion`, motion);
    setOrDelete(params, `${prefix}sort`, sort === defaults.sort ? "" : sort);
    setOrDelete(params, `${prefix}order`, order === defaults.order ? "" : order);
    setOrDelete(params, `${prefix}events`, recentOnly ? "recent" : "");
    window.history.replaceState(null, "", `${window.location.pathname}?${params}`);
  }, [prefix, search, quadrant, motion, sort, order, recentOnly]);
  return {
    search, quadrant, motion, sort, order, recentOnly,
    onSearch: setSearch,
    onQuadrant: setQuadrant,
    onMotion: setMotion,
    onSort: setSort,
    onOrder: setOrder,
    onRecentOnly: setRecentOnly,
    onReset: () => {
      setSearch(defaults.search);
      setQuadrant(defaults.quadrant);
      setMotion(defaults.motion);
      setSort(defaults.sort);
      setOrder(defaults.order);
      setRecentOnly(false);
    },
  };
}

function readInitial(prefix: string): RotationScreenOptions & { recentOnly: boolean } {
  const params = new URLSearchParams(window.location.search);
  return {
    search: params.get(`${prefix}search`) ?? "",
    quadrant: (params.get(`${prefix}quadrant`) ?? "") as Quadrant | "",
    motion: (params.get(`${prefix}motion`) ?? "") as MotionState | "",
    sort: (params.get(`${prefix}sort`) ?? "name") as RotationSortKey,
    order: params.get(`${prefix}order`) === "desc" ? "desc" : "asc",
    recentOnly: params.get(`${prefix}events`) === "recent",
  };
}

function setOrDelete(params: URLSearchParams, key: string, value: string) {
  if (value) params.set(key, value);
  else params.delete(key);
}
