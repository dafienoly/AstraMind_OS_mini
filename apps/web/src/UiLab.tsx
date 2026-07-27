import { useMemo, useState } from "react";

import {
  aggregateCandles,
  buildCandleFixture,
  decisionCutoff,
  type Timeframe,
  visibleAt,
} from "./market/candleFixture";
import { PriceChart } from "./market/PriceChart";
import { RangeSelector } from "./market/RangeSelector";

const destinations = ["今日", "市场", "策略竞技场", "组合", "系统"];
const states = ["加载中", "空数据", "数据陈旧", "受阻", "错误", "Shadow", "券商未连接"];
const timeframes: Timeframe[] = ["日线", "周线", "月线"];

export function UiLab() {
  const pointInTime = useMemo(
    () => visibleAt(buildCandleFixture(), decisionCutoff),
    [],
  );
  const [timeframe, setTimeframe] = useState<Timeframe>("日线");
  const aggregated = useMemo(
    () => aggregateCandles(pointInTime, timeframe),
    [pointInTime, timeframe],
  );
  const [range, setRange] = useState<[number, number]>([
    Math.max(0, aggregated.length - 54),
    aggregated.length - 1,
  ]);
  const safeEnd = Math.min(range[1], aggregated.length - 1);
  const safeStart = Math.min(range[0], Math.max(0, safeEnd - 1));
  const visible = aggregated.slice(safeStart, safeEnd + 1);

  function switchTimeframe(next: Timeframe) {
    const nextRows = aggregateCandles(pointInTime, next);
    setTimeframe(next);
    setRange([Math.max(0, nextRows.length - 54), Math.max(1, nextRows.length - 1)]);
  }

  return (
    <div className="lab">
      <header className="topbar">
        <a className="wordmark" href="/dev/ui-lab">
          ASTRA<span>MIND</span>
        </a>
        <nav aria-label="产品主导航">
          {destinations.map((item) => (
            <span key={item}>{item}</span>
          ))}
        </nav>
        <div className="mode-pill">研究模式 · 本地</div>
      </header>

      <main className="lab-main">
        <div className="lab-heading">
          <div>
            <p className="eyebrow">UI LAB / WP-0003</p>
            <h1>统一价格检查器</h1>
            <p>一张图完成区间、点时边界与价量关系检查。</p>
          </div>
          <div className="cutoff">
            <span>决策截止</span>
            <strong>{decisionCutoff}</strong>
            <small>未来数据已隔离</small>
          </div>
        </div>

        <section className="decision-strip" aria-label="重要状态样本">
          {states.map((state) => (
            <span key={state} data-state={state}>
              {state}
            </span>
          ))}
        </section>

        <section className="inspector">
          <div className="instrument-row">
            <div>
              <span className="instrument-code">SYNTHETIC.SZ</span>
              <strong>点时正确合成样本</strong>
              <small>仅用于组件验收，不代表真实证券</small>
            </div>
            <div className="timeframe" aria-label="K 线周期">
              {timeframes.map((item) => (
                <button
                  type="button"
                  className={item === timeframe ? "active" : ""}
                  onClick={() => switchTimeframe(item)}
                  key={item}
                >
                  {item}
                </button>
              ))}
            </div>
          </div>

          <PriceChart candles={visible} />
          <RangeSelector
            count={aggregated.length}
            start={safeStart}
            end={safeEnd}
            startLabel={aggregated[safeStart]?.time ?? "—"}
            endLabel={aggregated[safeEnd]?.time ?? "—"}
            onChange={(start, end) => setRange([start, end])}
          />
          <footer className="chart-note">
            <span><i className="up" />上涨 / 红</span>
            <span><i className="down" />下跌 / 绿</span>
            <span><i className="ma5" />MA 5</span>
            <span><i className="ma20" />MA 20</span>
            <p>价格序列按 {decisionCutoff} 截断后才进入周期聚合。</p>
          </footer>
        </section>
      </main>
    </div>
  );
}
