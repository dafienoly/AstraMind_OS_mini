import { useMemo, useState, type CSSProperties } from "react";

import { TechnicalDetails } from "../business-language/TechnicalDetails";
import { marketBusinessTexts } from "../business-language/marketBusinessText";
import type {
  IndustryHeatRow,
  MarketDashboardProjection,
  RealtimeIndustryHeat,
} from "./types";
import type { RealtimeMarketView } from "./useRealtimeMarket";

export function IndustryHeatView({
  projection,
  realtime,
}: {
  projection: MarketDashboardProjection;
  realtime: RealtimeMarketView;
}) {
  const rows = useMemo(
    () => [...projection.industries].sort(
      (left, right) => right.relative_strength - left.relative_strength,
    ),
    [projection.industries],
  );
  const [selectedCode, setSelectedCode] = useState(rows[0]?.industry_code ?? "");
  const selected = rows.find((item) => item.industry_code === selectedCode) ?? rows[0];
  const realtimeByIndustry = useMemo(
    () => new Map(
      (realtime.projection?.industries ?? []).map((item) => [item.industry_code, item]),
    ),
    [realtime.projection?.industries],
  );
  if (rows.length !== 31 || !selected) {
    return <section className="market-blocked">
      <p className="eyebrow">行业热力已阻断</p>
      <h1>一级行业覆盖不足</h1>
      <p>必须使用同一快照中的 31 个 SW2021 一级行业，不能用中心点或旧值补齐。</p>
    </section>;
  }
  const scale = Math.max(...rows.map((item) => Math.abs(item.relative_strength)), 0.01);
  return <div className="heat-layout">
    <section className="heat-sheet">
      <header className="market-sheet-heading">
        <div>
          <p className="eyebrow">SW2021 一级行业 / 相对当日均值</p>
          <h1>行业结构热力</h1>
          <p>颜色表达相对强弱；箭头、正负号和文字同时说明方向。</p>
        </div>
        <span className="heat-coverage">31 / 31 行业 · {projection.evidence_cutoff}</span>
      </header>
      <div className="heat-legend">
        <span>弱势 ↓</span><i /><span>行业均值</span><i /><span>强势 ↑</span>
      </div>
      <div className="heat-grid">
        {rows.map((row) => (
          <button
            aria-pressed={row.industry_code === selected.industry_code}
            data-direction={row.relative_strength >= 0 ? "up" : "down"}
            key={row.industry_code}
            onClick={() => setSelectedCode(row.industry_code)}
            style={{
              "--heat-alpha": `${12 + Math.abs(row.relative_strength) / scale * 55}%`,
            } as CSSProperties}
            type="button"
          >
            <span>{row.industry_name}</span>
            <strong>{signed(row.relative_strength)}%</strong>
            <small>{row.advancing} ↑ / {row.declining} ↓</small>
            {realtimeByIndustry.has(row.industry_code) ? <em>
              盘中 {signed(realtimeByIndustry.get(row.industry_code)!.change_percent)}%{" "}
              {realtime.effectiveState === "current" ? "临时" : "非当前"}
            </em> : null}
          </button>
        ))}
      </div>
    </section>
    <IndustryInspector
      realtime={realtime}
      realtimeHeat={realtimeByIndustry.get(selected.industry_code)}
      row={selected}
    />
  </div>;
}

function IndustryInspector({
  row,
  realtime,
  realtimeHeat,
}: {
  row: IndustryHeatRow;
  realtime: RealtimeMarketView;
  realtimeHeat: RealtimeIndustryHeat | undefined;
}) {
  return <aside className="market-inspector heat-inspector">
    <p className="eyebrow">选中行业检查器</p>
    <h2>{row.industry_name}</h2>
    <code>{row.industry_code}</code>
    <strong className={row.relative_strength >= 0 ? "return-up" : "return-down"}>
      相对行业均值 {signed(row.relative_strength)}% {row.relative_strength >= 0 ? "↑" : "↓"}
    </strong>
    <section className="realtime-inspector" data-state={realtime.effectiveState}>
      <small>盘中临时热度 · 不改写完成日排序</small>
      <strong>{realtimeHeat
        ? `${signed(realtimeHeat.change_percent)}% ${realtimeHeat.change_percent >= 0 ? "↑" : "↓"}`
        : "等待行业实时覆盖"}</strong>
      <p>{realtimeHeat
        ? `${realtimeHeat.observed_constituents} 个成分已观察`
        : realtime.message ?? "当前会话尚无该行业数据"}</p>
    </section>
    <dl>
      <div><dt>当日收益</dt><dd>{signed(row.percent_change)}%</dd></div>
      <div><dt>上涨 / 下跌成分</dt><dd>{row.advancing} / {row.declining}</dd></div>
      <div><dt>成分覆盖</dt><dd>{(row.coverage_ratio * 100).toFixed(0)}% · {row.covered_member_count}/{row.member_count}</dd></div>
      <div><dt>成交额相对 20 日</dt><dd>{formatRatio(row.amount_change_20d)}</dd></div>
      <div><dt>20 日波动</dt><dd>{row.volatility_20d?.toFixed(2) ?? "—"}%</dd></div>
      <div><dt>市盈率 / 市净率</dt><dd>{format(row.price_earnings)} / {format(row.price_book)}</dd></div>
    </dl>
    <section>
      <small>当日领先个股</small>
      <p>{row.leading_instrument_name ?? "覆盖不足"} {row.leading_instrument_id ?? ""}</p>
      <strong>{row.leading_percent_change === null ? "—" : `${signed(row.leading_percent_change)}%`}</strong>
    </section>
    {row.known_gaps.length ? <>
      <p className="heat-gap">
        覆盖提示：{marketBusinessTexts(row.known_gaps).join(" · ")}
      </p>
      <TechnicalDetails entries={[{ label: "缺口代码", value: row.known_gaps }]} />
    </> : null}
    <a href={`/market?tab=industries&view=rotation&industry=${encodeURIComponent(row.industry_code)}`}>
      查看相对轮动 →
    </a>
  </aside>;
}

function signed(value: number) {
  return `${value >= 0 ? "+" : ""}${value.toFixed(2)}`;
}

function format(value: number | null) {
  return value === null ? "—" : value.toFixed(2);
}

function formatRatio(value: number | null) {
  return value === null ? "—" : `${value >= 0 ? "+" : ""}${(value * 100).toFixed(1)}%`;
}
