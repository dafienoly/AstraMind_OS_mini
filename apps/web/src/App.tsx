import { useEffect, useState } from "react";

import { AppShell, useAppLocation } from "./app-shell/AppShell";
import { useRouteLoadPhase } from "./app-shell/routeProgress";
import { UiLab } from "./UiLab";
import { MarketPage } from "./market-dashboard/MarketPage";
import { OperationsShell } from "./operations/OperationsShell";
import { StockWorkbenchPage } from "./stock-workbench/StockWorkbenchPage";

type ApiState =
  | { kind: "loading" }
  | { kind: "ready"; version: string }
  | { kind: "error"; message: string };

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8010";

export function App() {
  const location = useAppLocation();
  if (location.pathname === "/dev/ui-lab") {
    return <UiLab />;
  }
  return <AppShell location={location}>
    <RouteContent pathname={location.pathname} />
  </AppShell>;
}

function RouteContent({ pathname }: { pathname: string }) {
  if (pathname === "/market") return <MarketPage />;
  if (pathname.startsWith("/stocks/")) return <StockWorkbenchPage />;
  if (pathname === "/today") return <OperationsShell destination="today" />;
  if (pathname === "/portfolio") return <OperationsShell destination="portfolio" />;
  if (pathname === "/execution") return <OperationsShell destination="execution" />;
  if (pathname === "/system") return <OperationsShell destination="system" />;
  if (pathname === "/strategy-arena") {
    return <PlannedPage
      eyebrow="策略竞技场"
      title="策略证据工作面仍在建设"
      detail="这里将比较策略版本、Research Shadow 与 Paper 证据；当前不会生成订单。"
    />;
  }
  return <FoundationDiagnostic />;
}

function FoundationDiagnostic() {
  const [apiState, setApiState] = useState<ApiState>({ kind: "loading" });

  useEffect(() => {
    const controller = new AbortController();

    fetch(`${apiBaseUrl}/healthz`, { signal: controller.signal })
      .then(async (response) => {
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }
        return (await response.json()) as { version: string; broker_enabled: boolean };
      })
      .then((payload) => {
        if (payload.broker_enabled) {
          throw new Error("受保护边界异常：券商不应启用");
        }
        setApiState({ kind: "ready", version: payload.version });
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted) {
          const message = error instanceof Error ? error.message : "未知错误";
          setApiState({ kind: "error", message });
        }
      });

    return () => controller.abort();
  }, []);
  useRouteLoadPhase(
    apiState.kind === "loading" ? "loading_content" : apiState.kind === "error" ? "error" : "ready",
    apiState.kind === "loading" ? "正在检查本地服务" : "本地服务检查完成",
  );

  return (
    <main className="foundation-diagnostic">
      <p className="eyebrow">ASTRAMIND OS MINI</p>
      <h1>本地量化交易工作台</h1>
      <p>行业相对轮动已经进入正式只读研究，其余产品界面仍按批准顺序实施。</p>
      <a href="/market?tab=industries&view=rotation">进入市场 · 行业相对轮动</a>
      <section aria-live="polite">
        <strong>API 状态：</strong>
        {apiState.kind === "loading" && "检查中"}
        {apiState.kind === "ready" && `已连接（v${apiState.version}，券商关闭）`}
        {apiState.kind === "error" && `不可用：${apiState.message}`}
      </section>
    </main>
  );
}

function PlannedPage({
  eyebrow,
  title,
  detail,
}: {
  eyebrow: string;
  title: string;
  detail: string;
}) {
  useRouteLoadPhase("ready", `${title}已就绪`);
  return <main className="planned-page">
    <p className="eyebrow">{eyebrow}</p>
    <h1>{title}</h1>
    <p>{detail}</p>
  </main>;
}
