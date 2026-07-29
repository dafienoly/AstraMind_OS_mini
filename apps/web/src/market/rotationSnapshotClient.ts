import type {
  RotationSortKey,
  RotationSortOrder,
} from "./rotationScreening";
import type {
  MotionState,
  Quadrant,
  RotationSnapshot,
  TrailMode,
} from "./rotationTypes";

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8010";

export type RotationLoadState =
  | { kind: "loading" }
  | { kind: "ready"; snapshot: RotationSnapshot }
  | { kind: "empty" }
  | { kind: "corrupt" }
  | { kind: "error"; message: string };

export interface RotationInitialParams {
  date: string | null;
  selected: string;
  trail: number;
  trailMode: TrailMode;
  quadrant: Quadrant | "";
  search: string;
  motion: MotionState | "";
  sort: RotationSortKey;
  order: RotationSortOrder;
  recentOnly: boolean;
}

let rotationRequest: Promise<RotationLoadState> | undefined;

export function loadRotationSnapshot(): Promise<RotationLoadState> {
  if (rotationRequest) return rotationRequest;
  const request = fetch(`${apiBaseUrl}/api/market/industry-rotation`, {
    cache: "no-store",
  })
    .then(async (response): Promise<RotationLoadState> => {
      if (response.status === 404) return { kind: "empty" };
      if (response.status === 503) return { kind: "corrupt" };
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      return { kind: "ready", snapshot: (await response.json()) as RotationSnapshot };
    })
    .catch((error: unknown): RotationLoadState => ({
      kind: "error",
      message: error instanceof Error ? error.message : "未知错误",
    }));
  rotationRequest = request;
  void request.then(() => {
    if (rotationRequest === request) rotationRequest = undefined;
  });
  return request;
}

export function readRotationInitialParams(): RotationInitialParams {
  const params = new URLSearchParams(window.location.search);
  const requestedTrailMode = params.get("trail_mode");
  return {
    date: params.get("as_of"),
    selected: params.get("industry") ?? "",
    trail: Number(params.get("trail")) || 20,
    trailMode: (
      requestedTrailMode === "filtered" || requestedTrailMode === "all"
        ? requestedTrailMode
        : "selected"
    ),
    quadrant: (params.get("quadrant") ?? "") as Quadrant | "",
    search: params.get("search") ?? "",
    motion: (params.get("motion") ?? "") as MotionState | "",
    sort: (params.get("sort") ?? "name") as RotationSortKey,
    order: params.get("order") === "desc" ? "desc" : "asc",
    recentOnly: params.get("events") === "recent",
  };
}
