import type { EtfRotationCandidate, RealtimeInstrumentQuote } from "../types";
import { etfCandidateStateLabel } from "./etfLabels";

export function EtfCandidateList({
  candidates,
  selected,
  onSelect,
  liveQuotes = new Map(),
}: {
  candidates: EtfRotationCandidate[];
  selected: string | null;
  onSelect: (code: string) => void;
  liveQuotes?: Map<string, RealtimeInstrumentQuote>;
}) {
  const visible = candidates
    .filter((item) => item.etf_code)
    .slice()
    .sort((left, right) => {
      const selectedOrder = Number(right.etf_code === selected) - Number(left.etf_code === selected);
      return selectedOrder || (right.overall_score ?? -1) - (left.overall_score ?? -1);
    });
  return <section className="etf-candidates">
    <header>
      <div>
        <p className="eyebrow">方向与 ETF</p>
        <h2>候选证据</h2>
      </div>
      <span>{visible.length} 只映射标的</span>
    </header>
    <div className="etf-candidate-scroll">
      {visible.map((item) => <button
        aria-pressed={item.etf_code === selected}
        className="etf-candidate"
        data-state={item.state}
        key={`${item.industry_code}-${item.etf_code}`}
        onClick={() => onSelect(item.etf_code ?? "")}
        type="button"
      >
        {(() => {
          const live = liveQuotes.get(item.etf_code ?? "");
          return <>
        <span>
          <strong>{item.etf_name ?? item.etf_code}</strong>
          <code>{item.etf_code}</code>
        </span>
        <span>
          <b>{item.industry_name}</b>
          <small>{item.lifecycle_stage} · {etfCandidateStateLabel(item.state)}</small>
        </span>
        <span className="etf-candidate-score">
          <b>{live?.last_price?.toFixed(3) ?? "—"}</b>
          <small>{live?.change_percent === null || live?.change_percent === undefined
            ? `研究 ${item.overall_score?.toFixed(1) ?? "—"}`
            : `${live.change_percent >= 0 ? "+" : ""}${live.change_percent.toFixed(2)}%`}</small>
        </span>
          </>;
        })()}
      </button>)}
    </div>
    <p className="etf-list-note">选择只更新价格核验，不创建目标或订单。</p>
  </section>;
}
