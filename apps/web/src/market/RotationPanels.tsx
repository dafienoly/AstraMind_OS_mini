import type { RotationSnapshot } from "./rotationTypes";
import { quadrantLabels } from "./rotationTypes";
import { assessRotationFreshness } from "./rotationFreshness";
import { industryColor } from "./rotationIdentity";

export const rotationSpeeds = [0.5, 1, 2] as const;

const trailOptions = [10, 20, 40, 60] as const;

export function RotationHeader({
  snapshot,
  onRefresh,
  refreshing,
}: {
  snapshot: RotationSnapshot;
  onRefresh: () => void;
  refreshing: boolean;
}) {
  const freshness = assessRotationFreshness(snapshot);
  const freshnessText = freshness.kind === "current"
    ? `${freshness.latestDate} 快照内完整`
    : freshness.kind === "stale"
      ? `${freshness.latestDate} 已过期 · 预期 ${freshness.expectedDate}`
      : `${freshness.latestDate} 已阻断 · ${freshness.reason}`;
  return <div className="rotation-status" data-state={freshness.kind}>
    <strong>数据</strong> {freshnessText}
    <button disabled={refreshing} onClick={onRefresh} type="button">
      {refreshing ? "刷新中…" : "刷新快照"}
    </button>
    {freshness.kind !== "current" ? <a href="/system">查看恢复状态</a> : null}
    <i /><strong>行业</strong> {snapshot.covered_industry_count}/{snapshot.industry_count}
    <i /><strong>公式</strong> {snapshot.formula.formula_version}
    <em>研究观察，不是买卖信号</em>
  </div>;
}

export function Playback(props: {
  dates: string[]; dateIndex: number; goToDate: (index: number) => void;
  playing: boolean;
  speed: import("./rotationTypes").RotationSpeed;
  setSpeed: (value: import("./rotationTypes").RotationSpeed) => void;
  trail: number; setTrail: (value: number) => void;
  reducedMotion: boolean;
  onPlayToggle: () => void;
  mode: import("./rotationTypes").PlaybackMode;
  onMode: (value: import("./rotationTypes").PlaybackMode) => void;
  continuousDuration: import("./rotationTypes").ContinuousDuration;
  onContinuousDuration: (value: import("./rotationTypes").ContinuousDuration) => void;
}) {
  const { dates, dateIndex, goToDate, playing, speed, setSpeed,
    trail, setTrail, reducedMotion } = props;
  return <section className="playback" aria-label="时间回放">
    <button type="button" onClick={props.onPlayToggle}>{playing ? "暂停" : "播放"}</button>
    <fieldset className="playback-mode">
      <legend>播放模式</legend>
      <button aria-pressed={props.mode === "daily"} onClick={() => props.onMode("daily")} type="button">逐日</button>
      <button aria-pressed={props.mode === "continuous"} disabled={reducedMotion}
        onClick={() => props.onMode("continuous")} type="button">整段</button>
    </fieldset>
    <button type="button" onClick={() => goToDate(Math.max(0, dateIndex - 1))}>上一日</button>
    <button type="button" onClick={() => goToDate(Math.min(dates.length - 1, dateIndex + 1))}>下一日</button>
    {props.mode === "daily" ? (
      <select aria-label="播放速度" value={speed} onChange={(event) => setSpeed(Number(event.target.value) as import("./rotationTypes").RotationSpeed)}>
        {rotationSpeeds.map((value) => <option key={value} value={value}>{value}x</option>)}
      </select>
    ) : (
      <select aria-label="整段播放时长" value={props.continuousDuration}
        onChange={(event) => props.onContinuousDuration(Number(event.target.value) as import("./rotationTypes").ContinuousDuration)}>
        {[10, 20, 40].map((value) => <option key={value} value={value}>{value} 秒</option>)}
      </select>
    )}
    <input aria-label="轮动日期" type="range" min="0" max={dates.length - 1} value={dateIndex}
      onChange={(event) => goToDate(Number(event.target.value))} />
    <time>{dates[dateIndex]}</time>
    <select aria-label="尾迹长度" value={trail} onChange={(event) => setTrail(Number(event.target.value))}>
      {trailOptions.map((value) => <option key={value} value={value}>尾迹 {value} 日</option>)}
    </select>
    <button type="button" onClick={() => goToDate(dates.length - 1)}>回到最新</button>
    {reducedMotion ? <small>已按系统偏好关闭插值动画</small> : null}
  </section>;
}

export function Inspector({ point, event, snapshot, onDrill }: {
  point: RotationSnapshot["points"][number] | undefined;
  event: RotationSnapshot["events"][number] | undefined;
  snapshot: RotationSnapshot;
  onDrill?: () => void;
}) {
  if (!point) return <aside className="rotation-inspector">
    <p className="eyebrow">行业总览</p>
    <h2>{snapshot.covered_industry_count} 个行业</h2>
    <p>选择任一行业查看轨迹、运动状态和层级入口。</p>
    <p>颜色只表达行业身份；箭头、双环和虚线表达运动状态。</p>
    <strong>研究观察，不是买卖信号</strong>
  </aside>;
  return <aside className="rotation-inspector" style={{
    borderTop: `3px solid ${industryColor(point.industry_code)}`,
  }}>
    <p className="eyebrow">选中行业检查器</p><h2>{point.industry_name}</h2><code>{point.industry_code}</code>
    <strong className={`quadrant-name quadrant-name--${point.quadrant}`}>{quadrantLabels[point.quadrant]}</strong>
    <dl>
      <div><dt>相对趋势</dt><dd>{point.relative_trend.toFixed(2)}</dd></div>
      <div><dt>相对动量</dt><dd>{point.relative_momentum.toFixed(2)}</dd></div>
      <div><dt>当日方向</dt><dd>{point.direction_x >= 0 ? "→" : "←"} {point.direction_y >= 0 ? "↑" : "↓"}</dd></div>
      <div><dt>覆盖</dt><dd>{(point.coverage * 100).toFixed(0)}% · {point.constituent_count} 个成分</dd></div>
    </dl>
    <section><small>最近确认跃迁</small><p>{event ? `${quadrantLabels[event.from_quadrant]} → ${quadrantLabels[event.to_quadrant]} · ${event.confirmed_date}` : "当前窗口无确认跃迁"}</p></section>
    {onDrill ? <button className="hierarchy-entry" onClick={onDrill} type="button">
      进入二级行业
    </button> : null}
    <details><summary>数据与方法</summary>
      <p>基准：31 个一级行业指数日收益等权</p>
      <p>EMA {snapshot.formula.fast_window}/{snapshot.formula.slow_window} · 动量 {snapshot.formula.momentum_window} 日</p>
      <p>这是一种价格相对强弱代理，不是直接资金净流入。</p>
      <code>{snapshot.content_hash}</code>
    </details>
  </aside>;
}

type StatusState =
  | { kind: "loading" }
  | { kind: "empty" }
  | { kind: "corrupt" }
  | { kind: "error"; message: string };

export function RotationStatus({ state }: { state: StatusState }) {
  const copy = state.kind === "loading" ? ["正在加载正式轮动快照", "读取一次有界证据，请稍候。"]
    : state.kind === "empty" ? ["尚无轮动快照", "先运行 make market-rotation 生成正式证据。"]
    : state.kind === "corrupt" ? ["轮动证据已阻断", "内容身份校验失败，请重建快照。"]
    : ["轮动服务不可用", `本地 API 返回异常：${state.message}`];
  return <main className="rotation-state"><p className="eyebrow">市场 / 行业 / 相对轮动</p>
    <h1>{copy[0]}</h1><p>{copy[1]}</p><strong>研究观察，不是买卖信号</strong></main>;
}
