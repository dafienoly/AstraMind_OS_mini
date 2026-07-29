import type {
  DailyAttentionItem,
  DailyOperations,
  DailyRunRequestAction,
  DailyRunStatus,
} from "./types";

export function DailyRunRail({ value }: { value: DailyOperations | null }) {
  const run = value?.latest_run;
  return (
    <section className="daily-run-panel" aria-label="日常运行">
      <header className="daily-run-header">
        <div>
          <p className="section-kicker">DAILY OPS</p>
          <h2>{run ? `${run.target_date} · ${runStateLabel(run.state)}` : "尚无运行记录"}</h2>
        </div>
        <span data-state={value?.schedule.state ?? "not_installed"}>
          计划任务 · {scheduleLabel(value?.schedule.state)}
        </span>
      </header>
      <div className="daily-run-rail">
        <RunStep label="数据" state={stepState(run, "data_pipeline")} />
        <RunStep label="决策" state={stepState(run, "decision_chain")} />
        <RunStep label="备份" state={stepState(run, "backup_readiness")} />
      </div>
      <dl className="daily-run-meta">
        <div><dt>下一次计划</dt><dd>{value?.schedule.next_run_at ? localTime(value.schedule.next_run_at) : "等待安装后计算"}</dd></div>
        <div><dt>待处理请求</dt><dd>{value?.pending_request ? requestLabel(value.pending_request.action) : "无"}</dd></div>
      </dl>
    </section>
  );
}

export function DailyAttentionInbox({
  items,
  onAction,
}: {
  items: DailyAttentionItem[];
  onAction: (action: DailyRunRequestAction) => void;
}) {
  return (
    <section className="daily-inbox" aria-label="日常运行异常收件箱">
      <header>
        <div><p className="section-kicker">需要你处理</p><h2>{items.length ? `${items.length} 项日常异常` : "日常运行无异常"}</h2></div>
      </header>
      {items.length === 0 ? <p className="daily-inbox-empty">数据、决策与备份没有需要人工介入的异常。</p> : (
        <div className="daily-inbox-list">
          {items.map((item) => (
            <article data-severity={item.severity} key={item.code}>
              <span aria-hidden="true">{item.severity === "blocked" ? "×" : "!"}</span>
              <div><h3>{item.title}</h3><p>{item.detail}</p></div>
              {isRunAction(item.action) ? (
                <button
                  className="quiet-button"
                  onClick={() => onAction(item.action as DailyRunRequestAction)}
                  type="button"
                >
                  {actionLabel(item.action)}
                </button>
              ) : item.action === "install_scheduler" ? <em>等待安装确认</em> : <em>查看状态</em>}
            </article>
          ))}
        </div>
      )}
    </section>
  );
}

export function DailyRunHistory({ runs }: { runs: DailyRunStatus[] }) {
  if (runs.length === 0) return null;
  return (
    <section className="daily-history" aria-label="最近运行">
      <p className="section-kicker">最近运行</p>
      {runs.map((run) => (
        <div key={run.run_id}>
          <time dateTime={run.target_date}>{run.target_date}</time>
          <strong>{runStateLabel(run.state)}</strong>
          <span>{run.completed_at ? localTime(run.completed_at) : "未完成"}</span>
        </div>
      ))}
    </section>
  );
}

function RunStep({ label, state }: { label: string; state: "pending" | "active" | "complete" | "blocked" }) {
  return <div data-state={state}><span aria-hidden="true" /><strong>{label}</strong><small>{stepLabel(state)}</small></div>;
}

function stepState(
  run: DailyRunStatus | null | undefined,
  step: "data_pipeline" | "decision_chain" | "backup_readiness",
): "pending" | "active" | "complete" | "blocked" {
  if (!run) return "pending";
  const complete = step === "data_pipeline" ? Boolean(run.data_commit_id)
    : step === "decision_chain" ? Boolean(run.order_plan_id)
    : Boolean(run.backup_id);
  if (complete) return "complete";
  if (run.current_step === step || run.state === "running") return "active";
  if (run.state === "blocked" || run.state === "recovery_required" || run.state === "stale") return "blocked";
  return "pending";
}

function isRunAction(value: DailyAttentionItem["action"]): value is DailyRunRequestAction {
  return value === "run" || value === "recover" || value === "retry_provider";
}

const runStateLabel = (value: DailyRunStatus["state"]) => ({
  waiting_window: "等待收盘窗口",
  waiting_provider: "等待提供方",
  running: "运行中",
  current: "已完成",
  stale: "已过时",
  blocked: "受阻",
  recovery_required: "需要恢复",
  lease_held: "已有实例运行",
})[value];

const stepLabel = (value: "pending" | "active" | "complete" | "blocked") => ({
  pending: "等待",
  active: "进行中",
  complete: "完成",
  blocked: "受阻",
})[value];

const scheduleLabel = (value?: DailyOperations["schedule"]["state"]) => ({
  not_installed: "未安装",
  installed: "已安装",
  paused: "已暂停",
  error: "异常",
})[value ?? "not_installed"];

const requestLabel = (value: DailyRunRequestAction) => ({
  run: "运行",
  recover: "恢复",
  retry_provider: "提供方重试",
})[value];

const actionLabel = (value: DailyRunRequestAction) => ({
  run: "登记运行",
  recover: "登记恢复",
  retry_provider: "登记重试",
})[value];

function localTime(value: string) {
  return new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(new Date(value));
}
