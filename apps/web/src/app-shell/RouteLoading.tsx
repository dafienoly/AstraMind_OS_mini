import type { RouteLoadReport } from "./types";

export function RouteLoading({
  report,
  slow,
}: {
  report: RouteLoadReport;
  slow: boolean;
}) {
  const active = report.phase !== "ready" && report.phase !== "error";
  return <>
    <div
      aria-hidden="true"
      className={`route-progress${active ? " is-active" : ""}`}
      data-phase={report.phase}
    />
    <div className="route-announcer" aria-live="polite" role="status">
      {active ? report.label : ""}
    </div>
    {slow && active ? <div className="route-loading-overlay" aria-busy="true">
      <section className="route-loading-stage">
        <span className="route-loading-mark" aria-hidden="true" />
        <div>
          <strong>{report.label}</strong>
          <small>{phaseCopy(report.phase)}</small>
        </div>
      </section>
      <div className="route-skeleton" aria-hidden="true">
        <i /><i /><i /><i /><i /><i />
      </div>
    </div> : null}
  </>;
}

function phaseCopy(phase: RouteLoadReport["phase"]) {
  if (phase === "connecting_realtime") return "正式证据已就绪，正在建立当前会话覆盖";
  if (phase === "loading_content") return "正在读取目标页面的不可变证据";
  return "正在切换工作面，导航和返回路径保持可用";
}
