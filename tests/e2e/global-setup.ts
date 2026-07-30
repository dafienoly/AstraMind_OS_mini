import { chromium, type FullConfig } from "@playwright/test";

const IMPORT_PATTERN = /(?:from\s*|import\s*\()\s*["']([^"']+)["']/g;

async function warmModuleGraph(url: URL, seen: Set<string>): Promise<void> {
  if (seen.has(url.href) || seen.size >= 160) return;
  seen.add(url.href);
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Vite warmup failed: ${response.status} ${url.pathname}`);
  }
  const source = await response.text();
  const dependencies = [...source.matchAll(IMPORT_PATTERN)]
    .map((match) => match[1])
    .filter((specifier): specifier is string => specifier?.startsWith("/") ?? false);
  await Promise.all(
    dependencies.map((specifier) => warmModuleGraph(new URL(specifier, url), seen)),
  );
}

export default async function warmRealStockRoute(config: FullConfig) {
  const configuredBaseUrl = config.projects[0]?.use.baseURL;
  const baseUrl = typeof configuredBaseUrl === "string"
    ? configuredBaseUrl
    : "http://127.0.0.1:5174";
  const route = new URL(
    "/stocks/000001.SZ?origin=watchlist&mode=completed&return_target=market_stocks",
    baseUrl,
  );
  const routeResponse = await fetch(route);
  if (!routeResponse.ok) {
    throw new Error(`Stock route warmup failed: ${routeResponse.status}`);
  }
  const seen = new Set<string>();
  await warmModuleGraph(new URL("/src/stock-workbench/StockWorkbenchPage.tsx", baseUrl), seen);
  await warmModuleGraph(
    new URL("/src/market-dashboard/realtime/RealtimeMinuteChart.tsx", baseUrl),
    seen,
  );

  const server = await chromium.launchServer();
  const endpoint = server.wsEndpoint();
  for (const project of config.projects) {
    (project.use as typeof project.use & {
      connectOptions?: { wsEndpoint: string };
    }).connectOptions = { wsEndpoint: endpoint };
  }
  return async () => server.close();
}
