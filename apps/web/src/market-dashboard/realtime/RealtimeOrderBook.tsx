import type { RealtimeInstrumentQuote } from "../types";

export function RealtimeOrderBook({ quote }: { quote: RealtimeInstrumentQuote | null }) {
  if (!quote) return <section className="realtime-orderbook empty">
    <h2>五档盘口</h2><p>等待所选证券行情。</p>
  </section>;
  return <section className="realtime-orderbook" aria-label="五档盘口">
    <header><div><p className="eyebrow">MiniQMT L1</p><h2>五档盘口</h2></div>
      <span data-state={quote.status_label === "正常交易" ? "current" : "stale"}>
        {quote.status_label}
      </span>
    </header>
    <dl className="realtime-limits">
      <div><dt>涨停</dt><dd>{price(quote.upper_limit)}</dd></div>
      <div><dt>跌停</dt><dd>{price(quote.lower_limit)}</dd></div>
    </dl>
    <div className="orderbook-levels">
      {[...quote.asks].reverse().map((row) => <div className="ask" key={`a${row.level}`}>
        <span>卖 {row.level}</span><strong>{price(row.price)}</strong><em>{volume(row.volume)}</em>
      </div>)}
      {quote.bids.map((row) => <div className="bid" key={`b${row.level}`}>
        <span>买 {row.level}</span><strong>{price(row.price)}</strong><em>{volume(row.volume)}</em>
      </div>)}
    </div>
    <footer>接收 {new Date(quote.received_at).toLocaleTimeString("zh-CN", { hour12: false })}</footer>
  </section>;
}

function price(value: number | null) {
  return value === null ? "—" : value.toFixed(3);
}

function volume(value: number | null) {
  if (value === null) return "—";
  return value >= 10_000 ? `${(value / 10_000).toFixed(1)}万` : value.toFixed(0);
}
