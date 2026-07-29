import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import type { RouteLoadPhase, RouteLoadReport } from "./types";

type RouteProgressValue = {
  report: (value: RouteLoadReport) => void;
  routeKey: string;
};

const RouteProgressContext = createContext<RouteProgressValue | null>(null);

export function RouteProgressProvider({
  children,
  routeKey,
  onReport,
}: {
  children: ReactNode;
  routeKey: string;
  onReport: (value: RouteLoadReport) => void;
}) {
  const value = useMemo(
    () => ({ report: onReport, routeKey }),
    [onReport, routeKey],
  );
  return <RouteProgressContext.Provider value={value}>
    {children}
  </RouteProgressContext.Provider>;
}

export function useRouteLoadPhase(phase: RouteLoadPhase, label: string) {
  const context = useContext(RouteProgressContext);
  useEffect(() => {
    context?.report({ phase, label });
  }, [context, label, phase]);
}

export function useSlowRoute(phase: RouteLoadPhase) {
  const [slow, setSlow] = useState(false);
  useEffect(() => {
    if (phase === "ready" || phase === "error") {
      setSlow(false);
      return;
    }
    const timer = window.setTimeout(() => setSlow(true), 300);
    return () => window.clearTimeout(timer);
  }, [phase]);
  return slow;
}
