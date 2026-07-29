import type {
  IndustryLifecycleProjection,
  IndustryLifecycleIntradayProjection,
  IndustryResearchRankingSnapshot,
  EtfRotationProjection,
  MarketDashboardProjection,
  RealtimeMarketProjection,
  RealtimeInstrumentDetail,
  RealtimeInstrumentProjection,
  RealtimeInstrumentSearchResult,
} from "./types";

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8010";
let cachedRequest: Promise<MarketDashboardProjection> | undefined;
let cachedFetch: typeof globalThis.fetch | undefined;
let cachedLifecycleRequest: Promise<IndustryLifecycleProjection> | undefined;
const cachedRankingRequests = new Map<string, Promise<IndustryResearchRankingSnapshot>>();
let cachedEtfRequest: Promise<EtfRotationProjection> | undefined;

export class MarketDashboardFetchError extends Error {
  constructor(
    readonly kind: "empty" | "error",
    message: string,
  ) {
    super(message);
    this.name = "MarketDashboardFetchError";
  }
}

export class RealtimeMarketFetchError extends Error {
  constructor(
    readonly kind: "empty" | "error",
    message: string,
  ) {
    super(message);
    this.name = "RealtimeMarketFetchError";
  }
}

export async function fetchMarketDashboard(
  signal?: AbortSignal,
  force = false,
): Promise<MarketDashboardProjection> {
  if (signal?.aborted) throw new DOMException("Aborted", "AbortError");
  if (cachedFetch !== globalThis.fetch) {
    cachedRequest = undefined;
    cachedFetch = globalThis.fetch;
  }
  if (!cachedRequest || force) {
    cachedRequest = requestMarketDashboard().catch((error: unknown) => {
      cachedRequest = undefined;
      throw error;
    });
  }
  return cachedRequest;
}

export async function fetchIndustryLifecycle(
  signal?: AbortSignal,
  force = false,
): Promise<IndustryLifecycleProjection> {
  if (signal?.aborted) throw new DOMException("Aborted", "AbortError");
  if (cachedFetch !== globalThis.fetch) {
    cachedRequest = undefined;
    cachedLifecycleRequest = undefined;
    cachedFetch = globalThis.fetch;
  }
  if (!cachedLifecycleRequest || force) {
    cachedLifecycleRequest = requestIndustryLifecycle().catch((error: unknown) => {
      cachedLifecycleRequest = undefined;
      throw error;
    });
  }
  return cachedLifecycleRequest;
}

export async function fetchIndustryLifecycleIntraday(
  signal?: AbortSignal,
): Promise<IndustryLifecycleIntradayProjection> {
  const response = await fetch(`${apiBaseUrl}/api/market/industry-lifecycle/intraday`, { signal });
  if (!response.ok) throw new RealtimeMarketFetchError(
    response.status === 404 ? "empty" : "error",
    response.status === 404 ? "等待盘中生命周期投影" : `盘中生命周期 HTTP ${response.status}`,
  );
  return (await response.json()) as IndustryLifecycleIntradayProjection;
}

export async function fetchIndustryRanking(
  dataSnapshotId: string,
  industryCode: string,
  instrumentId?: string,
  signal?: AbortSignal,
): Promise<IndustryResearchRankingSnapshot> {
  if (signal?.aborted) throw new DOMException("Aborted", "AbortError");
  if (cachedFetch !== globalThis.fetch) {
    cachedRequest = undefined;
    cachedLifecycleRequest = undefined;
    cachedRankingRequests.clear();
    cachedFetch = globalThis.fetch;
  }
  const query = new URLSearchParams({
    data_snapshot_id: dataSnapshotId,
    industry_code: industryCode,
  });
  if (instrumentId) query.set("instrument_id", instrumentId);
  const key = query.toString();
  const cached = cachedRankingRequests.get(key);
  if (cached) return cached;
  const request = requestIndustryRanking(key).catch((error: unknown) => {
    cachedRankingRequests.delete(key);
    throw error;
  });
  cachedRankingRequests.set(key, request);
  return request;
}

export async function fetchEtfRotation(
  signal?: AbortSignal,
  force = false,
): Promise<EtfRotationProjection> {
  if (signal?.aborted) throw new DOMException("Aborted", "AbortError");
  if (cachedFetch !== globalThis.fetch) {
    cachedEtfRequest = undefined;
    cachedFetch = globalThis.fetch;
  }
  if (!cachedEtfRequest || force) {
    cachedEtfRequest = requestEtfRotation().catch((error: unknown) => {
      cachedEtfRequest = undefined;
      throw error;
    });
  }
  return cachedEtfRequest;
}

export const realtimeMarketStreamUrl = `${apiBaseUrl}/api/market/realtime/stream`;

export function realtimeInstrumentStreamUrl(instrumentIds: string[]) {
  const query = new URLSearchParams({ instrument_ids: instrumentIds.join(",") });
  return `${apiBaseUrl}/api/market/realtime/instruments/stream?${query}`;
}

export async function fetchRealtimeInstruments(
  instrumentIds: string[] = [],
  industryCode?: string,
  instrumentType?: string,
  signal?: AbortSignal,
): Promise<RealtimeInstrumentProjection> {
  const query = new URLSearchParams();
  if (instrumentIds.length) query.set("instrument_ids", instrumentIds.join(","));
  if (industryCode) query.set("industry_code", industryCode);
  if (instrumentType) query.set("instrument_type", instrumentType);
  const response = await fetch(`${apiBaseUrl}/api/market/realtime/instruments?${query}`, { signal });
  if (!response.ok) throw new RealtimeMarketFetchError(
    response.status === 404 ? "empty" : "error",
    response.status === 404 ? "等待 MiniQMT 证券投影" : `实时证券 HTTP ${response.status}`,
  );
  return (await response.json()) as RealtimeInstrumentProjection;
}

export async function fetchRealtimeInstrumentDetail(
  instrumentId: string,
  signal?: AbortSignal,
): Promise<RealtimeInstrumentDetail> {
  const response = await fetch(
    `${apiBaseUrl}/api/market/realtime/instruments/${encodeURIComponent(instrumentId)}`,
    { signal },
  );
  if (!response.ok) throw new RealtimeMarketFetchError(
    response.status === 404 ? "empty" : "error",
    response.status === 404 ? "尚无该证券盘中数据" : `证券明细 HTTP ${response.status}`,
  );
  return (await response.json()) as RealtimeInstrumentDetail;
}

export async function fetchMarketWatchlist(signal?: AbortSignal): Promise<string[]> {
  const response = await fetch(`${apiBaseUrl}/api/market/watchlist`, { signal });
  if (!response.ok) throw new Error(`自选清单 HTTP ${response.status}`);
  return ((await response.json()) as { instrument_ids: string[] }).instrument_ids;
}

export async function saveMarketWatchlist(instrumentIds: string[]): Promise<string[]> {
  const response = await fetch(`${apiBaseUrl}/api/market/watchlist`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ instrument_ids: instrumentIds }),
  });
  if (!response.ok) throw new Error(`保存自选清单 HTTP ${response.status}`);
  return ((await response.json()) as { instrument_ids: string[] }).instrument_ids;
}

export async function searchRealtimeInstruments(
  query: string,
  signal?: AbortSignal,
): Promise<RealtimeInstrumentSearchResult[]> {
  const params = new URLSearchParams({ q: query, limit: "12" });
  const response = await fetch(
    `${apiBaseUrl}/api/market/realtime/instruments/search?${params}`,
    { signal },
  );
  if (!response.ok) throw new RealtimeMarketFetchError(
    response.status === 404 ? "empty" : "error",
    response.status === 404 ? "等待证券目录" : `证券搜索 HTTP ${response.status}`,
  );
  return (await response.json()) as RealtimeInstrumentSearchResult[];
}

export async function fetchRealtimeMarket(
  signal?: AbortSignal,
): Promise<RealtimeMarketProjection> {
  const response = await fetch(`${apiBaseUrl}/api/market/realtime`, { signal });
  if (!response.ok) {
    if (response.status === 404) {
      throw new RealtimeMarketFetchError("empty", "等待 MiniQMT 实时会话");
    }
    throw new RealtimeMarketFetchError("error", `实时市场 HTTP ${response.status}`);
  }
  return (await response.json()) as RealtimeMarketProjection;
}

async function requestIndustryRanking(query: string): Promise<IndustryResearchRankingSnapshot> {
  const response = await fetch(`${apiBaseUrl}/api/market/industry-ranking?${query}`);
  if (!response.ok) {
    if (response.status === 404) {
      throw new MarketDashboardFetchError("empty", "尚无正式行业排序快照");
    }
    throw new MarketDashboardFetchError("error", `HTTP ${response.status}`);
  }
  return (await response.json()) as IndustryResearchRankingSnapshot;
}

async function requestMarketDashboard(): Promise<MarketDashboardProjection> {
  const response = await fetch(`${apiBaseUrl}/api/market/dashboard`);
  if (!response.ok) {
    if (response.status === 404) {
      throw new MarketDashboardFetchError("empty", "尚无正式市场快照");
    }
    throw new MarketDashboardFetchError("error", `HTTP ${response.status}`);
  }
  return (await response.json()) as MarketDashboardProjection;
}

async function requestIndustryLifecycle(): Promise<IndustryLifecycleProjection> {
  const response = await fetch(`${apiBaseUrl}/api/market/industry-lifecycle`);
  if (!response.ok) {
    if (response.status === 404) {
      throw new MarketDashboardFetchError("empty", "尚无正式生命周期快照");
    }
    throw new MarketDashboardFetchError("error", `HTTP ${response.status}`);
  }
  return (await response.json()) as IndustryLifecycleProjection;
}

async function requestEtfRotation(): Promise<EtfRotationProjection> {
  const response = await fetch(`${apiBaseUrl}/api/market/etf-rotation`);
  if (!response.ok) {
    if (response.status === 404) {
      throw new MarketDashboardFetchError("empty", "尚无正式 ETF 轮动快照");
    }
    throw new MarketDashboardFetchError("error", `HTTP ${response.status}`);
  }
  return (await response.json()) as EtfRotationProjection;
}
