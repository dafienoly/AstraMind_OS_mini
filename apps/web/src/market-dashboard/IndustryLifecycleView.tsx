import { useEffect, useMemo, useState } from "react";

import {
  fetchIndustryLifecycle,
  fetchIndustryLifecycleIntraday,
  MarketDashboardFetchError,
} from "./marketDashboardClient";
import { IndustryRankingPanel } from "./IndustryRankingPanel";
import type {
  IndustryLifecyclePoint,
  IndustryLifecycleProjection,
  IndustryLifecycleIntradayProjection,
  LifecycleStage,
} from "./types";
import type { RealtimeMarketView } from "./useRealtimeMarket";

const stages: LifecycleStage[] = [
  "明显退潮",
  "退潮观察",
  "强势扩散",
  "低位修复",
  "极端低位",
  "方向未明",
];

type State =
  | { kind: "loading" }
  | { kind: "empty" | "error"; message: string }
  | { kind: "ready"; projection: IndustryLifecycleProjection };

export function IndustryLifecycleView({
  dashboardSnapshotId,
  realtime,
}: {
  dashboardSnapshotId: string;
  realtime: RealtimeMarketView;
}) {
  const [state, setState] = useState<State>({ kind: "loading" });
  const [intraday, setIntraday] = useState<IndustryLifecycleIntradayProjection | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    fetchIndustryLifecycle(controller.signal)
      .then((projection) => setState({ kind: "ready", projection }))
      .catch((error: unknown) => {
        if (!controller.signal.aborted) {
          setState({
            kind: error instanceof MarketDashboardFetchError ? error.kind : "error",
            message: error instanceof Error ? error.message : "未知错误",
          });
        }
      });
    return () => controller.abort();
  }, []);
  useEffect(() => {
    if (!realtime.projection) return;
    const controller = new AbortController();
    let timer = 0;
    const refresh = async () => {
      try {
        setIntraday(await fetchIndustryLifecycleIntraday(controller.signal));
      } catch {
        if (!controller.signal.aborted) setIntraday(null);
      }
      if (!controller.signal.aborted) timer = window.setTimeout(refresh, 2000);
    };
    timer = window.setTimeout(refresh, 350);
    return () => {
      controller.abort();
      window.clearTimeout(timer);
    };
  }, [realtime.projection?.session_id]);

  if (state.kind !== "ready") {
    return <section className="market-blocked lifecycle-state" aria-live="polite">
      <p className="eyebrow">市场 / 行业 / 生命周期结构</p>
      <h1>{state.kind === "loading" ? "正在计算行业结构" : state.kind === "empty"
        ? "尚无生命周期快照" : "生命周期服务不可用"}</h1>
      <p>{state.kind === "loading"
        ? "从同一不可变快照复算成分股位置、趋势和行业参与率。"
        : state.message}</p>
    </section>;
  }
  if (
    state.projection.status === "blocked"
    || state.projection.data_snapshot_id !== dashboardSnapshotId
  ) {
    return <LifecycleBlocked
      gaps={state.projection.data_snapshot_id === dashboardSnapshotId
        ? state.projection.known_gaps
        : ["dashboard_lifecycle_snapshot_mismatch"]}
    />;
  }
  return <LifecycleWorkspace intraday={intraday} projection={state.projection} />;
}

function LifecycleWorkspace({
  projection,
  intraday,
}: {
  projection: IndustryLifecycleProjection;
  intraday: IndustryLifecycleIntradayProjection | null;
}) {
  const available = projection.industries.filter((item) => item.strong_participation !== null);
  const restored = new URLSearchParams(window.location.search).get("lifecycleIndustry");
  const [selectedCode, setSelectedCode] = useState(
    available.some((item) => item.industry_code === restored)
      ? restored ?? ""
      : available[0]?.industry_code ?? "",
  );
  const [query, setQuery] = useState("");
  const [stage, setStage] = useState<LifecycleStage | "全部阶段">("全部阶段");
  const selected = projection.industries.find((item) => item.industry_code === selectedCode)
    ?? projection.industries[0];
  const filtered = useMemo(() => projection.industries.filter((item) => (
    (stage === "全部阶段" || item.stage === stage)
    && `${item.industry_name}${item.industry_code}`.toLowerCase().includes(query.toLowerCase())
  )), [projection.industries, query, stage]);

  useEffect(() => {
    const url = new URL(window.location.href);
    url.searchParams.set("lifecycleIndustry", selectedCode);
    window.history.replaceState(null, "", url);
  }, [selectedCode]);

  if (!selected) return <LifecycleBlocked gaps={["industry_registry_missing"]} />;
  return <section className="lifecycle-workspace">
    <header className="lifecycle-heading">
      <div>
        <p className="eyebrow">SW2021 L1 · {projection.evidence_cutoff}</p>
        <h1>{selected.industry_name} · {selected.stage}</h1>
        <p>
          强势参与 {percent(selected.strong_participation)} · 低位修复{" "}
          {percent(selected.low_participation)} · 覆盖 {percent(selected.coverage_ratio * 100)}
        </p>
      </div>
      <dl>
        <div><dt>方法</dt><dd>{projection.method_version}</dd></div>
        <div><dt>盘中端点</dt><dd>{intraday
          ? `${intraday.state === "current" ? "当前" : "非当前"} · ${intraday.method_version}`
          : "尚不可用"}</dd></div>
        <div><dt>置信度</dt><dd>{confidenceLabel(selected.confidence)}</dd></div>
        <div><dt>样本</dt><dd>{selected.valid_member_count}/{selected.eligible_member_count}</dd></div>
      </dl>
    </header>
    <div className="lifecycle-controls">
      <label>查找行业
        <input value={query} onChange={(event) => setQuery(event.target.value)}
          placeholder="名称或代码" type="search" />
      </label>
      <label>生命周期
        <select value={stage} onChange={(event) => setStage(event.target.value as typeof stage)}>
          <option>全部阶段</option>
          {stages.map((item) => <option key={item}>{item}</option>)}
        </select>
      </label>
      <span>{filtered.length} / {projection.industries.length} 行业</span>
      <em>研究观察，不是买卖信号</em>
    </div>
    <div className="lifecycle-layout">
      <LifecycleMap
        industries={filtered}
        intraday={intraday}
        selectedCode={selected.industry_code}
        onSelect={setSelectedCode}
      />
      <LifecycleIndex
        industries={filtered}
        selectedCode={selected.industry_code}
        onSelect={setSelectedCode}
      />
    </div>
    <IndustryRankingPanel
      dataSnapshotId={projection.data_snapshot_id}
      industryCode={selected.industry_code}
      lifecycleCutoff={projection.evidence_cutoff}
      taxonomyVersion={projection.taxonomy_version}
    />
  </section>;
}

function LifecycleMap({
  industries,
  intraday,
  selectedCode,
  onSelect,
}: {
  industries: IndustryLifecyclePoint[];
  intraday: IndustryLifecycleIntradayProjection | null;
  selectedCode: string;
  onSelect: (value: string) => void;
}) {
  const available = industries.filter(
    (item) => item.strong_participation !== null && item.low_participation !== null,
  );
  const labels = new Set(
    [...available]
      .sort((left, right) => (
        Number(right.industry_code === selectedCode) - Number(left.industry_code === selectedCode)
        || Math.abs((right.strong_change_5d ?? 0)) - Math.abs((left.strong_change_5d ?? 0))
        || (right.amount_share_20d ?? 0) - (left.amount_share_20d ?? 0)
      ))
      .slice(0, 9)
      .map((item) => item.industry_code),
  );
  const liveByIndustry = new Map(
    (intraday?.points ?? []).map((point) => [point.industry_code, point]),
  );
  return <div className="lifecycle-map-scroll">
    <svg className="lifecycle-map" role="img" aria-label="行业生命周期结构地图"
      viewBox="0 0 800 560">
      <title>强势参与率与低位修复参与率结构地图</title>
      <rect className="lifecycle-map-bg" x="70" y="30" width="690" height="470" />
      {[0, 25, 50, 75, 100].map((tick) => <g key={tick}>
        <line x1={70 + tick * 6.9} x2={70 + tick * 6.9} y1="30" y2="500" />
        <text x={70 + tick * 6.9} y="525" textAnchor="middle">{tick}%</text>
        <line x1="70" x2="760" y1={500 - tick * 4.7} y2={500 - tick * 4.7} />
        <text x="58" y={504 - tick * 4.7} textAnchor="end">{tick}%</text>
      </g>)}
      <text className="axis-title" x="415" y="552" textAnchor="middle">强势参与率 S →</text>
      <text className="axis-title" x="17" y="265" textAnchor="middle"
        transform="rotate(-90 17 265)">低位修复参与率 L →</text>
      {available.map((item) => {
        const x = 70 + (item.strong_participation ?? 0) * 6.9;
        const y = 500 - (item.low_participation ?? 0) * 4.7;
        const radius = 6 + 50 * Math.sqrt(Math.max(item.amount_share_20d ?? 0, 0));
        const live = liveByIndustry.get(item.industry_code);
        const liveX = live ? 70 + live.strong_participation * 6.9 : null;
        const liveY = live ? 500 - live.low_participation * 4.7 : null;
        return <g key={item.industry_code} className="lifecycle-node"
          data-stage={item.stage} data-confidence={item.confidence}
          aria-label={`${item.industry_name}，${item.stage}`}
          aria-pressed={item.industry_code === selectedCode}
          onClick={() => onSelect(item.industry_code)}
          onKeyDown={(event) => {
            if (event.key === "Enter" || event.key === " ") onSelect(item.industry_code);
          }}
          role="button" tabIndex={0}>
          {liveX !== null && liveY !== null ? <>
            <line className="lifecycle-intraday-line" x1={x} y1={y} x2={liveX} y2={liveY} />
            <circle className="lifecycle-intraday-point" cx={liveX} cy={liveY}
              r={Math.min(radius, 24) + 3} />
          </> : null}
          <circle cx={x} cy={y} r={Math.min(radius, 24)} />
          {labels.has(item.industry_code)
            ? <text x={x + Math.min(radius, 24) + 4} y={y + 4}>{item.industry_name}</text>
            : null}
        </g>;
      })}
    </svg>
  </div>;
}

function LifecycleIndex({
  industries,
  selectedCode,
  onSelect,
}: {
  industries: IndustryLifecyclePoint[];
  selectedCode: string;
  onSelect: (value: string) => void;
}) {
  return <aside className="lifecycle-index" aria-label="生命周期行业索引">
    <header><strong>行业索引</strong><span>S / L</span></header>
    <div>
      {industries.map((item) => <button key={item.industry_code}
        aria-pressed={item.industry_code === selectedCode}
        data-stage={item.stage}
        onClick={() => onSelect(item.industry_code)} type="button">
        <i />
        <span><strong>{item.industry_name}</strong><small>{item.stage}</small></span>
        <em>{shortPercent(item.strong_participation)} / {shortPercent(item.low_participation)}</em>
      </button>)}
    </div>
  </aside>;
}

function LifecycleBlocked({ gaps }: { gaps: string[] }) {
  return <section className="market-blocked">
    <p className="eyebrow">市场 / 行业 / 生命周期结构</p>
    <h1>当前快照不能形成一致的行业结构</h1>
    <p>行业身份仍被保留，但缺失证据不会作为零坐标显示。</p>
    <code>{gaps.join(" · ") || "lifecycle_projection_blocked"}</code>
  </section>;
}

function percent(value: number | null) {
  return value === null ? "不可用" : `${value.toFixed(1)}%`;
}

function shortPercent(value: number | null) {
  return value === null ? "—" : value.toFixed(0);
}

function confidenceLabel(value: IndustryLifecyclePoint["confidence"]) {
  return value === "high" ? "高" : value === "medium" ? "中" : "低";
}
