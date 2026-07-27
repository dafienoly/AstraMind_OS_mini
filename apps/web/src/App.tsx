import { useEffect, useState } from "react";

import { UiLab } from "./UiLab";

type ApiState =
  | { kind: "loading" }
  | { kind: "ready"; version: string }
  | { kind: "error"; message: string };

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8010";

export function App() {
  if (window.location.pathname === "/dev/ui-lab") {
    return <UiLab />;
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

  return (
    <main>
      <p className="eyebrow">WP-0001 开发诊断</p>
      <h1>产品界面尚未实现</h1>
      <p>当前页面只验证本地 API、React/Vite 与浏览器工具链。</p>
      <section aria-live="polite">
        <strong>API 状态：</strong>
        {apiState.kind === "loading" && "检查中"}
        {apiState.kind === "ready" && `已连接（v${apiState.version}，券商关闭）`}
        {apiState.kind === "error" && `不可用：${apiState.message}`}
      </section>
    </main>
  );
}
