import { marketBusinessTexts } from "../business-language/marketBusinessText";
import type { MarketModelStatusItem } from "../market-dashboard/model-evidence/types";

export type LineageKey = "v1" | "data" | "training" | "evidence" | "activation";
export type LineageState = "complete" | "current" | "pending" | "danger";

export interface LineageStep {
  key: LineageKey;
  label: string;
  state: LineageState;
}

const steps: ReadonlyArray<{ key: LineageKey; label: string }> = [
  { key: "v1", label: "规则 V1" },
  { key: "data", label: "数据门" },
  { key: "training", label: "生产训练" },
  { key: "evidence", label: "样本外证据" },
  { key: "activation", label: "只读激活" },
];

const dataReasons = [
  "training_data_blocked",
  "historical_membership_not_then_known",
  "historical_breadth_membership_not_then_known",
  "point_in_time_lifecycle_history_not_published",
  "official_benchmark_mapping_not_then_known",
  "official_tracking_benchmark_history_not_published",
  "observed_bid_ask_history_not_published",
];
const trainingReasons = [
  "v2_not_trained",
  "production_pipeline_unavailable",
  "artifact_incompatible",
  "v2_activation_invalid",
  "v2_referenced_artifact_invalid",
];
const evidenceReasons = ["trained_evidence_insufficient", "evidence_unsupported"];
const activationReasons = ["validated_pending_activation"];

export function currentMethod(item: MarketModelStatusItem | undefined) {
  if (!item) return "当前方法尚无已发布记录";
  if (item.state === "active_v2" || item.state === "unvalidated_v2") {
    return "学习模型 V2";
  }
  if (item.state === "fallback_v1") return "规则模型 V1";
  if (item.method_version === item.fallback_method_version) return "规则模型 V1（受阻）";
  return "当前方法状态受阻";
}

export function statusCopy(item: MarketModelStatusItem | undefined) {
  if (!item) return "该模型状态尚无已发布记录";
  if (item.state === "active_v2") return "学习模型 V2 已只读激活";
  if (item.state === "unvalidated_v2") return "V2 已发布，样本外证据待完成";
  if (item.state === "blocked") return "模型状态受阻，不能视为可用";
  const reasons = businessReasons(item);
  return reasons.length ? reasons.join("；") : "当前准确回退规则模型 V1";
}

export function businessReasons(item: MarketModelStatusItem | undefined) {
  return item ? marketBusinessTexts(item.reason_codes) : [];
}

export function statusTone(item: MarketModelStatusItem | undefined) {
  if (!item) return "unknown";
  if (item.reason_codes.some(isArtifactReason)) return "danger";
  if (item.state === "active_v2") return "active";
  if (item.state === "blocked") return "blocked";
  return item.state === "unvalidated_v2" ? "pending" : "fallback";
}

export function nextGateCopy(item: MarketModelStatusItem | undefined) {
  if (!item) return "下一道门：尚无足够已发布字段可定位";
  if (item.state === "active_v2") {
    return "只读激活已发布；这不代表策略晋级或交易资格";
  }
  if (item.state === "unvalidated_v2") return "下一道门：完成封存样本外证据";
  const focus = reasonGate(item.reason_codes);
  return {
    data: "下一道门：数据门尚未通过",
    training: "下一道门：生产训练尚未形成可用发布",
    evidence: "下一道门：样本外证据尚未支持",
    activation: "下一道门：等待只读激活记录",
    v1: "下一道门：尚无足够已发布字段可定位",
  }[focus ?? "v1"];
}

export function lineage(item: MarketModelStatusItem | undefined): LineageStep[] {
  if (!item) return steps.map((step) => ({ ...step, state: "pending" }));
  if (item.state === "active_v2") {
    return steps.map((step) => ({ ...step, state: "complete" }));
  }
  if (item.state === "unvalidated_v2") {
    return steps.map((step) => ({
      ...step,
      state: step.key === "evidence"
        ? "current"
        : step.key === "activation" ? "pending" : "complete",
    }));
  }
  const focus = reasonGate(item.reason_codes);
  const danger = item.reason_codes.some(isArtifactReason);
  return steps.map((step) => ({
    ...step,
    state: step.key === "v1"
      ? "complete"
      : step.key === focus ? (danger ? "danger" : "current") : "pending",
  }));
}

export function publishedTime(value: string | null | undefined) {
  if (!value) return "尚无已发布记录";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "尚无已发布记录";
  return new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(date);
}

function reasonGate(reasons: readonly string[]): LineageKey | null {
  if (reasons.some((reason) => dataReasons.includes(reason) || reason.startsWith("etf_data_gate_"))) {
    return "data";
  }
  if (reasons.some((reason) => trainingReasons.includes(reason))) return "training";
  if (reasons.some((reason) => evidenceReasons.includes(reason))) return "evidence";
  if (reasons.some((reason) => activationReasons.includes(reason))) return "activation";
  return null;
}

function isArtifactReason(reason: string) {
  return reason === "artifact_incompatible"
    || reason === "v2_activation_invalid"
    || reason === "v2_referenced_artifact_invalid";
}
