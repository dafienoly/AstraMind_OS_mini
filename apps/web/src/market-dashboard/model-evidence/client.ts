import type { MarketModelStatusProjection } from "./types";

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8010";
let cachedFetch: typeof globalThis.fetch | undefined;
let cachedRequest: Promise<MarketModelStatusProjection> | undefined;

export async function fetchMarketModelStatus(
  signal?: AbortSignal,
  force = false,
): Promise<MarketModelStatusProjection> {
  if (signal?.aborted) throw new DOMException("Aborted", "AbortError");
  if (cachedFetch !== globalThis.fetch) {
    cachedFetch = globalThis.fetch;
    cachedRequest = undefined;
  }
  if (!cachedRequest || force) {
    cachedRequest = requestStatus().catch((error: unknown) => {
      cachedRequest = undefined;
      throw error;
    });
  }
  return cachedRequest;
}

async function requestStatus() {
  const response = await fetch(`${apiBaseUrl}/api/market/model-status`);
  if (!response.ok) throw new Error(`模型状态 HTTP ${response.status}`);
  const value = await response.json() as MarketModelStatusProjection;
  if (!Array.isArray(value.models) || value.models.length !== 5) {
    throw new Error("模型状态契约不完整");
  }
  return value;
}
