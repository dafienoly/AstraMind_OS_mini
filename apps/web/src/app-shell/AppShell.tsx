import {
  startTransition,
  useCallback,
  useEffect,
  useLayoutEffect,
  useState,
  type ReactNode,
} from "react";

import {
  industryDestination,
  industryNavigation,
  marketDestination,
  marketNavigation,
  primaryDestination,
  primaryNavigation,
  readLocation,
  systemDestination,
  systemNavigation,
} from "./navigation";
import { RouteLoading } from "./RouteLoading";
import { RouteProgressProvider, useSlowRoute } from "./routeProgress";
import type { AppLocation, RouteLoadReport } from "./types";

export function AppShell({
  children,
  location,
}: {
  children: ReactNode;
  location: AppLocation;
}) {
  const [report, setReport] = useState<RouteLoadReport>({
    phase: "navigating",
    label: "正在打开工作面",
  });
  const slow = useSlowRoute(report.phase);
  const primary = primaryDestination(location);
  const market = marketDestination(location);
  const industry = industryDestination(location);
  const system = systemDestination(location);

  useLayoutEffect(() => {
    setReport({ phase: "navigating", label: routeLabel(location) });
  }, [location.key]);

  const onReport = useCallback((next: RouteLoadReport) => setReport(next), []);
  return <RouteProgressProvider
    onReport={onReport}
    routeKey={location.key}
  >
    <div className="app-shell">
      <header className="app-topbar">
        <a className="app-wordmark" href="/today">ASTRA<span>MIND</span></a>
        <nav aria-label="一级导航">
          {primaryNavigation.map((item) => <a
            aria-current={primary === item.id ? "page" : undefined}
            href={item.href}
            key={item.id}
          >{item.label}</a>)}
        </nav>
        <a className="app-attention" href="/today#attention">需要你处理</a>
      </header>
      {primary === "market" ? <nav className="app-market-nav" aria-label="市场视图">
        <span>市场</span>
        {marketNavigation.map((item) => <a
          aria-current={market === item.id ? "page" : undefined}
          href={item.href}
          key={item.id}
        >{item.label}</a>)}
        {market === "industries" ? <>
          <i />
          {industryNavigation.map((item) => <a
            aria-current={industry === item.id ? "page" : undefined}
            href={item.href}
            key={item.id}
          >{item.label}</a>)}
        </> : null}
      </nav> : null}
      {primary === "system" ? <nav
        className="app-market-nav app-system-nav"
        aria-label="系统视图"
      >
        <span>系统</span>
        {systemNavigation.map((item) => <a
          aria-current={system === item.id ? "page" : undefined}
          href={item.href}
          key={item.id}
        >{item.label}</a>)}
      </nav> : null}
      <RouteLoading report={report} slow={slow} />
      <div className="app-route-stage">{children}</div>
    </div>
  </RouteProgressProvider>;
}

export function useAppLocation() {
  const [location, setLocation] = useState(readLocation);
  useEffect(() => {
    const update = () => startTransition(() => setLocation(readLocation()));
    const onPopState = () => update();
    const onClick = (event: MouseEvent) => {
      const anchor = (event.target as Element | null)?.closest<HTMLAnchorElement>("a[href]")
        ?? null;
      if (!shouldHandle(event, anchor)) return;
      if (!anchor) return;
      const url = new URL(anchor.href);
      event.preventDefault();
      window.history.pushState(null, "", `${url.pathname}${url.search}${url.hash}`);
      update();
    };
    window.addEventListener("popstate", onPopState);
    document.addEventListener("click", onClick);
    return () => {
      window.removeEventListener("popstate", onPopState);
      document.removeEventListener("click", onClick);
    };
  }, []);
  return location;
}

export function AppShellLink({
  href,
  children,
  className,
}: {
  href: string;
  children: ReactNode;
  className?: string;
}) {
  return <a className={className} href={href}>{children}</a>;
}

function shouldHandle(event: MouseEvent, anchor: HTMLAnchorElement | null) {
  if (!anchor || event.defaultPrevented || event.button !== 0) return false;
  if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return false;
  if (anchor.target && anchor.target !== "_self") return false;
  if (anchor.hasAttribute("download")) return false;
  const url = new URL(anchor.href);
  return url.origin === window.location.origin;
}

function routeLabel(location: AppLocation) {
  if (location.pathname.startsWith("/stocks/")) return "正在打开通用个股工作面";
  if (location.pathname === "/market") {
    const tab = marketDestination(location);
    if (tab === "etf") return "正在进入 ETF 轮动";
    if (tab === "stocks") return "正在进入个股观察";
    if (tab === "industries") return "正在进入行业工作面";
    return "正在进入大盘";
  }
  if (location.pathname === "/system/method-status") return "正在读取方法与状态";
  if (location.pathname.startsWith("/system")) return "正在进入系统工作面";
  return "正在切换工作面";
}
