import { useEffect, useState } from "react";

import {
  fetchRealtimeMarket,
  RealtimeMarketFetchError,
  realtimeMarketStreamUrl,
} from "./marketDashboardClient";
import type { RealtimeMarketProjection } from "./types";

export type RealtimeMarketView = {
  phase: "loading" | "empty" | "ready" | "error";
  connection: "connecting" | "connected" | "disconnected";
  projection: RealtimeMarketProjection | null;
  message: string | null;
  effectiveState: "current" | "stale" | "disconnected";
};

const initialState: RealtimeMarketView = {
  phase: "loading",
  connection: "connecting",
  projection: null,
  message: null,
  effectiveState: "disconnected",
};

export function useRealtimeMarket(): RealtimeMarketView {
  const [view, setView] = useState<RealtimeMarketView>(initialState);

  useEffect(() => {
    const controller = new AbortController();
    let disposed = false;
    let receivedStreamEvent = false;
    const updateProjection = (projection: RealtimeMarketProjection) => {
      if (disposed) return;
      receivedStreamEvent = true;
      setView({
        phase: "ready",
        connection: "connected",
        projection,
        message: null,
        effectiveState: effectiveState(projection),
      });
    };
    const source = openRealtimeStream(
      updateProjection,
      (message) => {
        if (disposed) return;
        setView((current) => ({
          ...current,
          phase: current.projection ? "ready" : "empty",
          connection: "disconnected",
          message,
          effectiveState: "disconnected",
        }));
      },
      () => {
        if (disposed) return;
        setView((current) => ({
          ...current,
          connection: "connected",
          effectiveState: current.projection
            ? effectiveState(current.projection)
            : "disconnected",
        }));
      },
    );
    void fetchRealtimeMarket(controller.signal)
      .then((projection) => {
        if (!disposed && !receivedStreamEvent) {
          setView({
            phase: "ready",
            connection: source ? "connecting" : "disconnected",
            projection,
            message: null,
            effectiveState: effectiveState(projection),
          });
        }
      })
      .catch((error: unknown) => {
        if (!disposed && !controller.signal.aborted && !receivedStreamEvent) {
          const empty = error instanceof RealtimeMarketFetchError && error.kind === "empty";
          setView({
            phase: empty ? "empty" : "error",
            connection: source ? "connecting" : "disconnected",
            projection: null,
            message: error instanceof Error ? error.message : "实时市场服务不可用",
            effectiveState: "disconnected",
          });
        }
      });
    return () => {
      disposed = true;
      controller.abort();
      source?.close();
    };
  }, []);

  return view;
}

function effectiveState(
  projection: RealtimeMarketProjection,
): RealtimeMarketView["effectiveState"] {
  if (projection.operational_state === "disconnected") return "disconnected";
  return projection.operational_state === "updating" ? "current" : "stale";
}

type StreamEvent = MessageEvent<string>;

function openRealtimeStream(
  onProjection: (projection: RealtimeMarketProjection) => void,
  onDisconnected: (message: string) => void,
  onOpen: () => void,
): EventSource | null {
  if (typeof globalThis.EventSource === "undefined") return null;
  const source = new EventSource(realtimeMarketStreamUrl);
  source.onopen = onOpen;
  source.onerror = () => onDisconnected("连接已断开，浏览器正在自动重连");
  source.addEventListener("market", ((event: StreamEvent) => {
    try {
      onProjection(JSON.parse(event.data) as RealtimeMarketProjection);
    } catch {
      onDisconnected("实时消息格式无效");
    }
  }) as EventListener);
  source.addEventListener("status", ((event: StreamEvent) => {
    try {
      const status = JSON.parse(event.data) as { state?: string };
      if (status.state === "disconnected") {
        onDisconnected("尚无可用 MiniQMT 实时会话");
      }
    } catch {
      onDisconnected("实时状态消息格式无效");
    }
  }) as EventListener);
  return source;
}
