import { useCallback, useEffect, useState } from "react";

import { fetchMarketModelStatus } from "./client";
import type { MarketModelFamily, MarketModelStatusItem } from "./types";

type State =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ready"; item: MarketModelStatusItem; asOf: string };

export function useMarketModelStatus(family: MarketModelFamily) {
  const [state, setState] = useState<State>({ kind: "loading" });
  const load = useCallback(async (signal?: AbortSignal, force = false) => {
    setState({ kind: "loading" });
    try {
      const projection = await fetchMarketModelStatus(signal, force);
      if (signal?.aborted) return;
      const item = projection.models.find((model) => model.model_family === family);
      if (!item) throw new Error("当前工作面的模型身份缺失");
      setState({ kind: "ready", item, asOf: projection.as_of });
    } catch (error) {
      if (!signal?.aborted) {
        setState({
          kind: "error",
          message: error instanceof Error ? error.message : "模型状态未知",
        });
      }
    }
  }, [family]);
  useEffect(() => {
    const controller = new AbortController();
    void load(controller.signal);
    return () => controller.abort();
  }, [load]);
  return { state, refresh: () => void load(undefined, true) };
}
