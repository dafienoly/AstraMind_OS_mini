import { useEffect, useMemo, useState } from "react";

import {
  fetchRealtimeInstrumentDetail,
  fetchRealtimeInstruments,
  realtimeInstrumentStreamUrl,
} from "../marketDashboardClient";
import type {
  RealtimeInstrumentDetail,
  RealtimeInstrumentProjection,
} from "../types";

export function useRealtimeInstruments(instrumentIds: string[]) {
  const key = useMemo(() => [...instrumentIds].sort().join(","), [instrumentIds]);
  const [projection, setProjection] = useState<RealtimeInstrumentProjection | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    if (!instrumentIds.length) {
      setProjection(null);
      return;
    }
    if (typeof EventSource === "undefined") return;
    const controller = new AbortController();
    void fetchRealtimeInstruments(instrumentIds, undefined, undefined, controller.signal)
      .then((value) => {
        setProjection(value);
        setMessage(null);
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted) setMessage(
          error instanceof Error ? error.message : "实时证券不可用",
        );
      });
    const source = new EventSource(realtimeInstrumentStreamUrl(instrumentIds));
    source.addEventListener("instruments", (event) => {
      setProjection(JSON.parse((event as MessageEvent<string>).data) as RealtimeInstrumentProjection);
      setMessage(null);
    });
    source.onerror = () => setMessage("实时连接已断开，正在自动重连");
    return () => {
      controller.abort();
      source.close();
    };
  }, [key]);
  return { projection, message };
}

export function useRealtimeInstrumentDetail(instrumentId: string | null) {
  const [detail, setDetail] = useState<RealtimeInstrumentDetail | null>(null);
  const { projection, message } = useRealtimeInstruments(instrumentId ? [instrumentId] : []);
  useEffect(() => {
    if (!instrumentId) {
      setDetail(null);
      return;
    }
    const controller = new AbortController();
    void fetchRealtimeInstrumentDetail(instrumentId, controller.signal)
      .then(setDetail)
      .catch(() => setDetail(null));
    return () => controller.abort();
  }, [instrumentId]);
  const quote = projection?.quotes[0] ?? detail?.quote ?? null;
  const open = projection?.open_minutes.filter((row) => row.instrument_id === instrumentId) ?? [];
  const minutes = useMemo(() => {
    const values = new Map((detail?.minutes ?? []).map((row) => [row.minute, row]));
    for (const row of open) values.set(row.minute, row);
    return [...values.values()].sort((left, right) => left.minute.localeCompare(right.minute));
  }, [detail?.minutes, open]);
  return {
    detail: detail ? { ...detail, quote: quote ?? detail.quote, minutes } : null,
    quote,
    minutes,
    state: projection?.state ?? detail?.state ?? "disconnected",
    message,
  };
}
