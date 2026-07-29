import { useEffect, useId, useState } from "react";

import { searchRealtimeInstruments } from "../marketDashboardClient";
import type { RealtimeInstrumentSearchResult } from "../types";

export function StockSearchCombobox({
  watchlist,
  onAdd,
}: {
  watchlist: string[];
  onAdd: (instrumentId: string) => void;
}) {
  const listId = useId();
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<RealtimeInstrumentSearchResult[]>([]);
  const [active, setActive] = useState(0);
  const [phase, setPhase] = useState<"idle" | "loading" | "ready" | "error">("idle");

  useEffect(() => {
    const value = query.trim();
    if (!value) {
      setResults([]);
      setPhase("idle");
      return;
    }
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      setPhase("loading");
      void searchRealtimeInstruments(value, controller.signal)
        .then((items) => {
          setResults(items);
          setActive(0);
          setPhase("ready");
        })
        .catch(() => {
          if (!controller.signal.aborted) {
            setResults([]);
            setPhase("error");
          }
        });
    }, 160);
    return () => {
      controller.abort();
      window.clearTimeout(timer);
    };
  }, [query]);

  const selected = results[active];
  const open = query.trim().length > 0 && phase !== "idle";
  const choose = (item: RealtimeInstrumentSearchResult) => {
    if (!watchlist.includes(item.instrument_id)) onAdd(item.instrument_id);
    setQuery("");
    setResults([]);
    setPhase("idle");
  };
  return <div className="stock-search">
    <label htmlFor={`${listId}-input`}>添加自选</label>
    <div className="stock-search-input">
      <input
        aria-activedescendant={selected ? `${listId}-${active}` : undefined}
        aria-autocomplete="list"
        aria-controls={listId}
        aria-expanded={open}
        autoComplete="off"
        id={`${listId}-input`}
        onBlur={() => window.setTimeout(() => setPhase("idle"), 120)}
        onChange={(event) => setQuery(event.target.value)}
        onFocus={() => {
          if (query.trim() && results.length) setPhase("ready");
        }}
        onKeyDown={(event) => {
          if (event.key === "ArrowDown" && results.length) {
            event.preventDefault();
            setActive((value) => (value + 1) % results.length);
          } else if (event.key === "ArrowUp" && results.length) {
            event.preventDefault();
            setActive((value) => (value - 1 + results.length) % results.length);
          } else if (event.key === "Enter" && selected) {
            event.preventDefault();
            choose(selected);
          } else if (event.key === "Escape") {
            setPhase("idle");
          }
        }}
        placeholder="输入代码或名称"
        role="combobox"
        value={query}
      />
      <span aria-live="polite">
        {phase === "loading" ? "匹配中…" : phase === "error" ? "搜索不可用" : ""}
      </span>
    </div>
    {open ? <ul className="stock-search-results" id={listId} role="listbox">
      {phase === "ready" && !results.length
        ? <li className="stock-search-empty">没有匹配的在市证券</li>
        : results.map((item, index) => {
          const exists = watchlist.includes(item.instrument_id);
          return <li
            aria-selected={index === active}
            id={`${listId}-${index}`}
            key={item.instrument_id}
            onMouseDown={(event) => {
              event.preventDefault();
              choose(item);
            }}
            role="option"
          >
            <span><strong>{item.instrument_name ?? item.instrument_id}</strong>
              <code>{item.instrument_id}</code></span>
            <span><b>{item.last_price?.toFixed(3) ?? "—"}</b>
              <small>{item.status_label}</small></span>
            <em>{exists ? "已在自选" : "加入"}</em>
          </li>;
        })}
    </ul> : null}
  </div>;
}
