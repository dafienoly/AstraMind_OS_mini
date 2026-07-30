import { useCallback, useEffect, useState } from "react";

import { fetchMarketModelStatus } from "../market-dashboard/model-evidence/client";
import type {
  MarketModelFamily,
  MarketModelStatusProjection,
} from "../market-dashboard/model-evidence/types";

type FailureKind = "empty" | "disconnected" | "blocked" | "error";

export type MethodStatusLoadState =
  | { kind: "loading" }
  | { kind: FailureKind; message: string }
  | {
      kind: "ready";
      projection: MarketModelStatusProjection;
      refreshing: boolean;
      refreshWarning: string | null;
    };

export function useMethodStatusProjection() {
  const [state, setState] = useState<MethodStatusLoadState>({ kind: "loading" });

  const load = useCallback(async (signal?: AbortSignal, force = false) => {
    setState((current) => current.kind === "ready"
      ? { ...current, refreshing: true, refreshWarning: null }
      : { kind: "loading" });
    try {
      const projection = await fetchMarketModelStatus(signal, force);
      if (signal?.aborted) return;
      assertReadonlyProjection(projection);
      setState({
        kind: "ready",
        projection,
        refreshing: false,
        refreshWarning: null,
      });
    } catch (error) {
      if (signal?.aborted) return;
      const failure = classifyFailure(error);
      setState((current) => current.kind === "ready"
        ? {
            ...current,
            refreshing: false,
            refreshWarning: `刷新失败：${failure.message}。仍显示上一次成功投影。`,
          }
        : failure);
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    void load(controller.signal);
    return () => controller.abort();
  }, [load]);

  return {
    state,
    refresh: () => void load(undefined, true),
  };
}

function assertReadonlyProjection(projection: MarketModelStatusProjection) {
  if (
    projection.broker_actions_allowed !== false
    || projection.models.some((item) => item.broker_actions_allowed !== false)
  ) {
    throw new ReadonlyBoundaryError();
  }
  const families = projection.models.map((item) => item.model_family);
  const expectedFamilies: MarketModelFamily[] = [
    "industry_heat",
    "industry_rotation",
    "industry_lifecycle",
    "industry_research_ranking",
    "etf_rotation",
  ];
  const modelStates = ["active_v2", "unvalidated_v2", "fallback_v1", "blocked"];
  const evidenceStates = [
    "development_only",
    "unvalidated",
    "supported",
    "unsupported",
    "blocked",
  ];
  if (
    new Set(families).size !== expectedFamilies.length
    || expectedFamilies.some((family) => !families.includes(family))
    || !projection.status_id
    || !validPublishedTime(projection.as_of)
    || projection.models.some((item) => (
      !modelStates.includes(item.state)
      || !evidenceStates.includes(item.evidence_state)
      || typeof item.method_version !== "string"
      || typeof item.fallback_method_version !== "string"
      || !Array.isArray(item.reason_codes)
      || (item.effective_at !== null && !validPublishedTime(item.effective_at))
    ))
  ) {
    throw new ProjectionContentError();
  }
}

function classifyFailure(error: unknown): { kind: FailureKind; message: string } {
  if (error instanceof ReadonlyBoundaryError) {
    return { kind: "blocked", message: "只读边界声明异常，状态已失败关闭" };
  }
  if (error instanceof ProjectionContentError) {
    return { kind: "blocked", message: "模型状态内容损坏，状态已失败关闭" };
  }
  const message = error instanceof Error ? error.message : "模型状态读取失败";
  const normalized = message.toLowerCase();
  if (normalized.includes("契约不完整")) {
    return { kind: "empty", message: "五类模型状态尚无完整发布记录" };
  }
  if (
    error instanceof TypeError
    || normalized.includes("failed to fetch")
    || normalized.includes("network")
  ) {
    return { kind: "disconnected", message: "本地模型状态服务连接中断" };
  }
  return { kind: "error", message };
}

class ReadonlyBoundaryError extends Error {}
class ProjectionContentError extends Error {}

function validPublishedTime(value: string) {
  return typeof value === "string" && !Number.isNaN(new Date(value).getTime());
}
