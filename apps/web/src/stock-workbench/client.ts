import type { StockFocusRequest } from "./focus";
import type { StockWorkbenchProjection } from "./types";

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8010";

export async function fetchStockWorkbench(
  instrumentId: string,
  request: StockFocusRequest,
  signal?: AbortSignal,
): Promise<StockWorkbenchProjection> {
  const query = new URLSearchParams({
    origin: request.origin,
    mode: request.mode,
    return_target: request.returnTarget,
  });
  if (request.dataSnapshotId) query.set("data_snapshot_id", request.dataSnapshotId);
  if (request.asOf) query.set("as_of", request.asOf);
  if (request.industryCode) query.set("industry_code", request.industryCode);
  const response = await fetch(
    `${apiBaseUrl}/api/market/stocks/${encodeURIComponent(instrumentId)}?${query}`,
    { signal },
  );
  if (!response.ok) throw new Error(
    response.status === 404
      ? "当前数据快照中没有这只证券"
      : `个股工作面 HTTP ${response.status}`,
  );
  return (await response.json()) as StockWorkbenchProjection;
}
