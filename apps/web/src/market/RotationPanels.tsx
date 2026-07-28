import type { RotationSnapshot } from "./rotationTypes";
import { quadrantLabels } from "./rotationTypes";

export const rotationSpeeds = [0.5, 1, 2] as const;
export type RotationSpeed = (typeof rotationSpeeds)[number];

const trailOptions = [10, 20, 40, 60] as const;

export function RotationHeader({ snapshot }: { snapshot: RotationSnapshot }) {
  return <><header className="rotation-topbar">
    <a href="/">ASTRAMIND <span>/ MINI</span></a>
    <nav><span>今日</span><strong>市场</strong><span>策略竞技场</span><span>组合</span><span>系统</span></nav>
    <span className="readonly">只读研究</span>
  </header><div className="rotation-status">
    <strong>数据</strong> {snapshot.date_range[1]} 快照内完整
    <i /><strong>行业</strong> {snapshot.covered_industry_count}/{snapshot.industry_count}
    <i /><strong>公式</strong> {snapshot.formula.formula_version}
    <em>研究观察，不是买卖信号</em>
  </div></>;
}

export function Playback(props: {
  dates: string[]; dateIndex: number; setDateIndex: (index: number) => void;
  playing: boolean; setPlaying: (value: boolean) => void;
  speed: RotationSpeed; setSpeed: (value: RotationSpeed) => void;
  trail: number; setTrail: (value: number) => void;
}) {
  const { dates, dateIndex, setDateIndex, playing, setPlaying, speed, setSpeed, trail, setTrail } = props;
  return <section className="playback" aria-label="时间回放">
    <button type="button" onClick={() => setPlaying(!playing)}>{playing ? "暂停" : "播放"}</button>
    <button type="button" onClick={() => { setPlaying(false); setDateIndex(Math.max(0, dateIndex - 1)); }}>上一日</button>
    <button type="button" onClick={() => { setPlaying(false); setDateIndex(Math.min(dates.length - 1, dateIndex + 1)); }}>下一日</button>
    <select aria-label="播放速度" value={speed} onChange={(event) => setSpeed(Number(event.target.value) as RotationSpeed)}>
      {rotationSpeeds.map((value) => <option key={value} value={value}>{value}x</option>)}
    </select>
    <input aria-label="轮动日期" type="range" min="0" max={dates.length - 1} value={dateIndex}
      onChange={(event) => { setPlaying(false); setDateIndex(Number(event.target.value)); }} />
    <time>{dates[dateIndex]}</time>
    <select aria-label="尾迹长度" value={trail} onChange={(event) => setTrail(Number(event.target.value))}>
      {trailOptions.map((value) => <option key={value} value={value}>尾迹 {value} 日</option>)}
    </select>
    <button type="button" onClick={() => { setPlaying(false); setDateIndex(dates.length - 1); }}>回到最新</button>
  </section>;
}

export function Inspector({ point, event, snapshot }: {
  point: RotationSnapshot["points"][number] | undefined;
  event: RotationSnapshot["events"][number] | undefined;
  snapshot: RotationSnapshot;
}) {
  if (!point) return <aside className="rotation-inspector">当前日期没有可用行业点。</aside>;
  return <aside className="rotation-inspector">
    <p className="eyebrow">选中行业检查器</p><h2>{point.industry_name}</h2><code>{point.industry_code}</code>
    <strong className={`quadrant-name quadrant-name--${point.quadrant}`}>{quadrantLabels[point.quadrant]}</strong>
    <dl>
      <div><dt>相对趋势</dt><dd>{point.relative_trend.toFixed(2)}</dd></div>
      <div><dt>相对动量</dt><dd>{point.relative_momentum.toFixed(2)}</dd></div>
      <div><dt>当日方向</dt><dd>{point.direction_x >= 0 ? "→" : "←"} {point.direction_y >= 0 ? "↑" : "↓"}</dd></div>
      <div><dt>覆盖</dt><dd>{(point.coverage * 100).toFixed(0)}% · {point.constituent_count} 个成分</dd></div>
    </dl>
    <section><small>最近确认跃迁</small><p>{event ? `${quadrantLabels[event.from_quadrant]} → ${quadrantLabels[event.to_quadrant]} · ${event.confirmed_date}` : "当前窗口无确认跃迁"}</p></section>
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
