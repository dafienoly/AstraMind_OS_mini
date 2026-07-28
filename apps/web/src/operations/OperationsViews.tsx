import type { ReactNode } from "react";

import type { PaperOperations } from "./types";

export function TodayView({ value }: { value: PaperOperations }) {
  return (
    <main className="ops-main">
      <PageHeading eyebrow="TODAY / 2026-07-28" title="下一动作很明确" copy={value.next_action} />
      <section className="timeline" aria-label="今日决策时间线">
        <TimelineStep label="目标" title={`${value.instrument_id ?? "尚无证券"} · 买入`}>
          来自不可变目标组合；计划数量 {value.quantity ?? 0} 股。
        </TimelineStep>
        <TimelineStep label="授权" title="StandingMandate 已建立">
          最大单笔 {money(value.max_notional_cny)}，只允许一笔金丝雀。
        </TimelineStep>
        <TimelineStep label="窗口" title={windowLabel(value)}>
          窗口外不提交；窗口内仍需新鲜卖一和确切限价批准。
        </TimelineStep>
        <TimelineStep label="券商" title="没有发生写入" blocked>
          当前委托意图 {value.intent_count}，券商观察 {value.observation_count}。
        </TimelineStep>
      </section>
      <AttentionBand value={value} />
    </main>
  );
}

export function PortfolioView({ value }: { value: PaperOperations }) {
  return (
    <main className="ops-main">
      <PageHeading
        eyebrow="PORTFOLIO / TACTICAL"
        title="当前、目标与待执行分开看"
        copy="既有模拟盘持仓只进入账户风险；只有本系统确认成交的新增数量进入 managed。"
      />
      <section className="holding-bridge" aria-label="当前到目标持仓桥">
        <BridgeColumn label="当前" value={`${value.inherited_position_count} 个 inherited 持仓`}>
          不自动归因、不自动卖出
        </BridgeColumn>
        <span className="bridge-arrow" aria-hidden="true">→</span>
        <BridgeColumn label="目标" value={`${value.instrument_id ?? "—"} · ${value.quantity ?? 0}股`}>
          允许与 inherited 重合
        </BridgeColumn>
        <span className="bridge-arrow" aria-hidden="true">→</span>
        <BridgeColumn label="待执行" value={`${value.intent_count} 笔`}>
          确切限价尚未批准
        </BridgeColumn>
      </section>
      <RiskLadder />
    </main>
  );
}

export function ExecutionView({ value }: { value: PaperOperations }) {
  return (
    <main className="ops-main">
      <PageHeading
        eyebrow="EXECUTION / PAPER"
        title="一笔金丝雀，一条恢复路径"
        copy="Shadow、Paper、Live 使用同一语义，但当前只允许 simulation。"
      />
      <div className="execution-grid">
        <section className="order-sheet" aria-label="金丝雀订单计划">
          <header><span>证券</span><strong>{value.instrument_id ?? "—"}</strong></header>
          <dl>
            <div><dt>方向 / 数量</dt><dd>买入 / {value.quantity ?? 0}股</dd></div>
            <div><dt>订单类型</dt><dd>限价</dd></div>
            <div><dt>金额上限</dt><dd>{money(value.max_notional_cny)}</dd></div>
            <div><dt>限价</dt><dd className="pending-value">等待窗口内确认</dd></div>
            <div><dt>重复提交</dt><dd>禁止</dd></div>
            <div><dt>撤单范围</dt><dd>仅本单</dd></div>
          </dl>
        </section>
        <section className="reconcile-sheet" aria-label="执行与对账">
          <p className="section-kicker">执行与对账</p>
          <h2>{stateLabel(value.canary_state)}</h2>
          <p>{value.next_action}</p>
          <div className="event-counts">
            <span><strong>{value.intent_count}</strong> 本地意图</span>
            <span><strong>{value.observation_count}</strong> 券商事实</span>
            <span><strong>{value.open_order_count}</strong> 未完成委托</span>
          </div>
          <p className="safe-note">未确认时只查询恢复，不自动重提。</p>
        </section>
      </div>
      <AttentionBand value={value} />
    </main>
  );
}

export function SystemView({
  value,
  onRefresh,
}: {
  value: PaperOperations;
  onRefresh: () => void;
}) {
  return (
    <main className="ops-main">
      <PageHeading
        eyebrow="SYSTEM / LOCAL"
        title="只显示今天是否可运行"
        copy="账户标识、Token、Windows 路径和原始券商载荷不会出现在这里。"
      />
      <div className="system-columns">
        <section>
          <p className="section-kicker">运行证据</p>
          <StatusLine label="Paper 账户基线" value={value.account_baseline_state} />
          <StatusLine label="MiniQMT 会话" value={value.broker_connection} />
          <StatusLine label="StandingMandate" value={stateLabel(value.canary_state)} />
          <StatusLine label="未完成委托" value={`${value.open_order_count} 笔`} />
        </section>
        <section>
          <p className="section-kicker">恢复</p>
          <h2>先读事实，再决定动作</h2>
          <p>重启后先查询账户、委托和成交；任何未知提交都不能直接重提。</p>
          <button className="quiet-button" onClick={onRefresh} type="button">刷新本地投影</button>
        </section>
      </div>
      <AttentionBand value={value} />
    </main>
  );
}

function PageHeading({ eyebrow, title, copy }: { eyebrow: string; title: string; copy: string }) {
  return <header className="ops-heading"><p className="eyebrow">{eyebrow}</p><h1>{title}</h1><p>{copy}</p></header>;
}

function TimelineStep({ label, title, children, blocked = false }: {
  label: string; title: string; children: ReactNode; blocked?: boolean;
}) {
  return <article data-blocked={blocked}><span>{label}</span><div><h2>{title}</h2><p>{children}</p></div></article>;
}

function BridgeColumn({ label, value, children }: { label: string; value: string; children: string }) {
  return <article><span>{label}</span><strong>{value}</strong><p>{children}</p></article>;
}

function RiskLadder() {
  return (
    <section className="risk-ladder" aria-label="回撤动作阶梯">
      <p className="section-kicker">回撤动作</p>
      <div><strong>8%</strong><span>警告 · 禁止扩大总风险</span></div>
      <div><strong>10%</strong><span>冻结新开仓 · 只持有或减仓</span></div>
      <div><strong>12%</strong><span>冻结全部买入 · 清仓建议等待人工决定</span></div>
    </section>
  );
}

function AttentionBand({ value }: { value: PaperOperations }) {
  return <aside className="attention-band" aria-label="需要你处理"><span>需要你处理</span><strong>{value.blocker_codes.length} 项</strong><p>{value.next_action}</p></aside>;
}

function StatusLine({ label, value }: { label: string; value: string }) {
  return <div className="status-line"><span>{label}</span><strong>{value}</strong></div>;
}

export function stateLabel(state: PaperOperations["canary_state"]) {
  return {
    not_authorized: "未授权",
    awaiting_final_limit_approval: "等待确切限价批准",
    ready_to_submit: "可提交",
    working: "执行中",
    terminal: "已收敛",
    blocked: "受阻",
  }[state];
}

function windowLabel(value: PaperOperations) {
  if (!value.submission_window_start || !value.submission_window_end) return "尚无提交窗口";
  return `${formatTime(value.submission_window_start)}–${formatTime(value.submission_window_end)}`;
}

export function formatTime(value: string) {
  return new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai", hour: "2-digit", minute: "2-digit", hour12: false,
  }).format(new Date(value));
}

function money(value: number | null) {
  return value === null ? "—" : `¥${value.toLocaleString("zh-CN")}`;
}
