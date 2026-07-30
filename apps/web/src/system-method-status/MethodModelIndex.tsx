import type {
  MarketModelFamily,
  MarketModelStatusItem,
} from "../market-dashboard/model-evidence/types";
import { methodCatalog } from "./methodCatalog";
import {
  currentMethod,
  publishedTime,
  statusCopy,
  statusTone,
} from "./methodStatusPresentation";

export function MethodModelIndex({
  selected,
  items,
  projectionTime,
  loading,
  onSelect,
}: {
  selected: MarketModelFamily;
  items: readonly MarketModelStatusItem[];
  projectionTime: string | null;
  loading: boolean;
  onSelect: (family: MarketModelFamily) => void;
}) {
  return <aside className="method-model-index" aria-label="五类模型索引">
    <header>
      <p className="section-kicker">MODEL INDEX</p>
      <h2>五类模型</h2>
    </header>
    <div>
      {methodCatalog.map((entry) => {
        const item = uniqueItem(items, entry.family);
        return <button
          aria-pressed={selected === entry.family}
          data-tone={loading ? "loading" : statusTone(item)}
          key={entry.family}
          onClick={() => onSelect(entry.family)}
          type="button"
        >
          <strong>{entry.label}</strong>
          <span>{loading ? "正在读取状态" : statusCopy(item)}</span>
          <small>
            {loading ? "当前方法读取中" : currentMethod(item)}
            {" · "}
            状态投影 {publishedTime(projectionTime)}
          </small>
        </button>;
      })}
    </div>
    <footer>
      <span>状态不是交易资格</span>
      <span>V2 激活也不自动晋级策略</span>
    </footer>
  </aside>;
}

export function uniqueItem(
  items: readonly MarketModelStatusItem[],
  family: MarketModelFamily,
) {
  const matches = items.filter((item) => item.model_family === family);
  return matches.length === 1 ? matches[0] : undefined;
}
