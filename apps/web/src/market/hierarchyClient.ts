import type { IndustryHierarchyView, RotationSnapshot } from "./rotationTypes";

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8010";

const hierarchyRequests = new Map<string, Promise<IndustryHierarchyView>>();

export function clearHierarchyRequests() {
  hierarchyRequests.clear();
}

export function loadHierarchy(url: string): Promise<IndustryHierarchyView> {
  const existing = hierarchyRequests.get(url);
  if (existing) return existing;
  const request = fetch(url)
    .then(async (response) => {
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      return response.json() as Promise<IndustryHierarchyView>;
    })
    .catch((error: unknown) => {
      if (hierarchyRequests.get(url) === request) hierarchyRequests.delete(url);
      throw error;
    });
  hierarchyRequests.set(url, request);
  return request;
}

export function hierarchyUrl(
  snapshot: RotationSnapshot,
  asOf: string,
  parentCode: string,
  allL2: boolean,
  l2Code: string,
  instrument: string,
) {
  const params = new URLSearchParams({
    data_snapshot_id: snapshot.data_snapshot_id,
    as_of: asOf,
    parent_code: parentCode,
    all_l2: String(allL2),
  });
  if (l2Code) params.set("l2_code", l2Code);
  if (instrument) params.set("instrument_id", instrument);
  return `${apiBaseUrl}/api/market/industry-hierarchy?${params}`;
}

export function canRetainStockWorkbench(
  view: IndustryHierarchyView | null,
  l2Code: string,
): IndustryHierarchyView | null {
  return view?.status === "ready" && view.level === "stock" && l2Code
    ? view
    : null;
}

export function retainNavigationEvidence(
  previous: IndustryHierarchyView | null,
  next: IndustryHierarchyView,
): IndustryHierarchyView {
  if (
    previous?.status !== "ready"
    || previous.level !== "stock"
    || next.status !== "ready"
    || next.level !== "stock"
    || previous.benchmark_id !== next.benchmark_id
    || previous.as_of !== next.as_of
  ) return next;
  return { ...next, nodes: previous.nodes, rotation: previous.rotation };
}

export function replaceHierarchyUrl(l2Code: string, instrument: string) {
  const url = new URL(window.location.href);
  if (l2Code) url.searchParams.set("l2", l2Code);
  else url.searchParams.delete("l2");
  if (instrument) url.searchParams.set("stock", instrument);
  else url.searchParams.delete("stock");
  window.history.replaceState(null, "", url);
}
