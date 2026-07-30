import { TechnicalDetails } from "../business-language/TechnicalDetails";
import { marketBusinessTexts } from "../business-language/marketBusinessText";
import type {
  MarketModelStatusItem,
  MarketModelStatusProjection,
} from "../market-dashboard/model-evidence/types";
import type { MethodCatalogEntry } from "./methodCatalog";
import {
  businessReasons,
  currentMethod,
  lineage,
  nextGateCopy,
  publishedTime,
  statusCopy,
  statusTone,
} from "./methodStatusPresentation";
import type { MethodStatusLoadState } from "./useMethodStatusProjection";

export function MethodStatusDetail({
  catalog,
  item,
  projection,
  state,
  onRetry,
}: {
  catalog: MethodCatalogEntry;
  item: MarketModelStatusItem | undefined;
  projection: MarketModelStatusProjection | null;
  state: MethodStatusLoadState;
  onRetry: () => void;
}) {
  if (state.kind !== "ready") {
    return <UnavailableState state={state} onRetry={onRetry} />;
  }
  const reasons = businessReasons(item);
  const knownGaps = marketBusinessTexts(projection?.known_gaps ?? []);
  return <section
    aria-label={`${catalog.label}方法状态`}
    className="method-status-detail"
    data-state={item?.state ?? "missing"}
    data-tone={statusTone(item)}
  >
    <header className="method-detail-heading">
      <div>
        <p className="section-kicker">SELECTED METHOD</p>
        <h2>{catalog.label}</h2>
        <p>{catalog.target}</p>
      </div>
      <span className="method-state-tag" data-tone={statusTone(item)}>
        {currentMethod(item)}
      </span>
    </header>

    <div className="method-definitions">
      <div><span>规则 V1</span><p>{catalog.v1}</p></div>
      <div><span>学习 V2</span><p>{catalog.v2}</p></div>
    </div>

    <Lineage item={item} />

    <div className="method-status-facts">
      <section>
        <p className="section-kicker">准确主方法</p>
        <h3>{currentMethod(item)}</h3>
        <p>{statusCopy(item)}</p>
        <small>数据门口径：{catalog.dataGate}</small>
      </section>
      <section>
        <p className="section-kicker">已发布时间语义</p>
        <dl>
          <TimeRow label="状态投影时间" value={publishedTime(projection?.as_of)} />
          <TimeRow label="方法生效时间" value={publishedTime(item?.effective_at)} />
          <TimeRow label="数据日期" value="尚无已发布记录" />
          <TimeRow label="行情 / 接收时间" value="尚无已发布记录" />
          <TimeRow label="训练 / 证据截止" value="尚无已发布记录" />
        </dl>
      </section>
    </div>

    <section className="method-gap-explanation">
      <p className="section-kicker">WHY THIS METHOD</p>
      <h3>{item?.state === "active_v2"
        ? "为什么当前使用 V2？"
        : "为什么还不能使用 V2？"}</h3>
      <p>{reasons.length
        ? reasons.join("；")
        : item?.state === "active_v2"
          ? "支持性证据和只读激活记录已发布。"
          : "尚无已发布的回退原因记录。"}</p>
      <strong>{nextGateCopy(item)}</strong>
      {knownGaps.length > 0
        ? <small>投影已知缺口：{knownGaps.join("；")}</small>
        : <small>投影没有发布额外的全局缺口。</small>}
    </section>

    <div className="method-detail-actions">
      <a href="/system">前往数据与作业</a>
      <TechnicalDetails entries={[
        { label: "状态投影身份", value: projection?.status_id },
        { label: "模型族枚举", value: item?.model_family },
        { label: "状态枚举", value: item?.state },
        { label: "证据状态枚举", value: item?.evidence_state },
        { label: "当前方法版本", value: item?.method_version },
        { label: "V1 回退版本", value: item?.fallback_method_version },
        { label: "模型清单身份", value: item?.manifest_id ?? "尚无已发布记录" },
        { label: "证据包身份", value: item?.evidence_bundle_id ?? "尚无已发布记录" },
        { label: "原因代码", value: item?.reason_codes },
        { label: "输入版本", value: "尚无已发布记录" },
        { label: "投影已知缺口代码", value: projection?.known_gaps },
      ]} />
    </div>
  </section>;
}

function Lineage({ item }: { item: MarketModelStatusItem | undefined }) {
  return <section className="method-lineage" aria-label="方法谱系尺">
    <header>
      <span>方法谱系尺</span>
      <strong>{nextGateCopy(item)}</strong>
    </header>
    <div className="method-lineage-scroll">
      <ol>
        {lineage(item).map((step) => <li
          aria-label={`${step.label}：${lineageStateLabel(step.state)}`}
          data-state={step.state}
          key={step.key}
        ><i aria-hidden="true" /><span>{step.label}</span></li>)}
      </ol>
    </div>
  </section>;
}

function TimeRow({ label, value }: { label: string; value: string }) {
  return <div><dt>{label}</dt><dd>{value}</dd></div>;
}

function UnavailableState({
  state,
  onRetry,
}: {
  state: Exclude<MethodStatusLoadState, { kind: "ready" }>;
  onRetry: () => void;
}) {
  const copy = {
    loading: ["正在读取五类模型状态", "等待只读状态投影返回。"],
    empty: ["尚无完整发布记录", state.kind === "empty" ? state.message : ""],
    disconnected: ["本地状态服务已断开", state.kind === "disconnected" ? state.message : ""],
    blocked: ["状态已失败关闭", state.kind === "blocked" ? state.message : ""],
    error: ["模型状态读取失败", state.kind === "error" ? state.message : ""],
  }[state.kind];
  return <section
    aria-live="polite"
    className="method-status-unavailable"
    data-state={state.kind}
  >
    <p className="section-kicker">METHOD STATUS</p>
    <h2>{copy[0]}</h2>
    <p>{copy[1]}</p>
    <p>未知或不完整状态不会显示为可用，规则 V1 也不会在这里被擅自推断。</p>
    {state.kind !== "loading"
      ? <button onClick={onRetry} type="button">重新读取状态</button>
      : <div className="method-status-skeleton" aria-hidden="true"><i /><i /><i /></div>}
  </section>;
}

function lineageStateLabel(state: "complete" | "current" | "pending" | "danger") {
  return {
    complete: "已有发布记录",
    current: "当前待通过",
    pending: "尚无通过记录",
    danger: "制品或身份异常",
  }[state];
}
