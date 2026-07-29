import { describe, expect, it } from "vitest";

import {
  marketBusinessText,
  marketBusinessTexts,
  UNKNOWN_BUSINESS_STATE,
} from "./marketBusinessText";

describe("market business language facade", () => {
  it.each([
    ["ready", "数据可用"],
    ["unavailable", "暂无可用数据"],
    ["date-bound-cutover", "历史行情与实时行情已衔接"],
    ["miniqmt", "MiniQMT 实时行情"],
    ["CURRENT", "正在更新"],
    ["STALE", "更新延迟"],
    ["DISCONNECTED", "实时连接中断"],
    [
      "historical_membership_not_then_known",
      "缺少当时可知的历史行业归属，暂不能进行严格历史验证",
    ],
    [
      "v2_not_trained",
      "学习模型尚未形成生产结果，当前使用规则模型",
    ],
    [
      "production_pipeline_unavailable",
      "生产训练功能尚未接通，当前使用规则模型",
    ],
    [
      "artifact_incompatible",
      "模型制品损坏或输入版本不兼容，当前使用规则模型",
    ],
  ])("maps %s to stable business text", (code, expected) => {
    expect(marketBusinessText(code)).toBe(expected);
  });

  it("describes dynamic gaps without exposing their payload", () => {
    expect(marketBusinessText("missing_dataset:daily_market"))
      .toBe("当前数据版本缺少必要数据集");
    expect(marketBusinessText("stock_rotation_incomplete_panel_excluded:11:codes"))
      .toBe("有 11 只股票因行情不完整未进入同业比较");
  });

  it("fails closed for unregistered internal codes", () => {
    expect(marketBusinessText("brand_new_internal_code")).toBe(UNKNOWN_BUSINESS_STATE);
  });

  it("deduplicates repeated business explanations", () => {
    expect(marketBusinessTexts(["missing_dataset:a", "missing_dataset:b"]))
      .toEqual(["当前数据版本缺少必要数据集"]);
  });
});
