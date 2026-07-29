import type { ReactNode } from "react";

import { TechnicalDetails } from "../business-language/TechnicalDetails";
import type { RotationSnapshot } from "./rotationTypes";

export function RotationFormulaDrawer({
  snapshot,
  onClose,
}: {
  snapshot: RotationSnapshot;
  onClose: () => void;
}) {
  const formula = snapshot.formula;
  return (
    <aside aria-label="公式与口径" className="rotation-formula">
      <p className="eyebrow">公式与口径</p>
      <h2>价格相对强弱，而非资金净流入</h2>
      <FormulaStep label="01 · 日收益与等权基准">
        <code>rᵢ,ₜ = ln(Pᵢ,ₜ / Pᵢ,ₜ₋₁)</code>
        <code>bₜ = mean(r₁,ₜ … rₙ,ₜ)</code>
      </FormulaStep>
      <FormulaStep label="02 · 累计相对状态与趋势">
        <code>Sᵢ,ₜ = Sᵢ,ₜ₋₁ + rᵢ,ₜ − bₜ</code>
        <code>Tᵢ,ₜ = EMA{formula.fast_window}(S) − EMA{formula.slow_window}(S)</code>
      </FormulaStep>
      <FormulaStep label={`03 · ${formula.momentum_window} 日动量`}>
        <code>Mᵢ,ₜ = Tᵢ,ₜ − Tᵢ,ₜ₋{formula.momentum_window}</code>
      </FormulaStep>
      <FormulaStep label="04 · 每日横截面稳健标准化">
        <code>z = (x − median) / (1.4826 × MAD)</code>
        <small>MAD 退化时使用总体标准差；仍为零则阻断发布。</small>
      </FormulaStep>
      <FormulaStep label="05 · 可视坐标">
        <code>
          逻辑 X/Y = 100 + {formula.scale} × clip(raw_z, −{formula.clip_z}, {formula.clip_z})
        </code>
        <code>显示 X/Y = 100 + 14 × tanh(raw_z / 2.5)</code>
        <small>显示变换：rotation-display-tanh-v1.0.0；只改变画布位置，不改变象限、事件或研究证据。</small>
        <p className="formula-warning">
          旧快照缺少 raw_z 时继续使用原逻辑坐标，不静默重写历史证据。
        </p>
      </FormulaStep>
      <dl>
        <div><dt>基准</dt><dd>{snapshot.benchmark_id}</dd></div>
        <div><dt>公式</dt><dd>{formula.formula_version}</dd></div>
        <div><dt>分类</dt><dd>{snapshot.taxonomy_version}:L1</dd></div>
        <div><dt>覆盖</dt><dd>{snapshot.covered_industry_count}/{snapshot.industry_count}</dd></div>
        <div><dt>事件</dt><dd>中性带 ±{formula.neutral_band} · 连续 {formula.confirmation_sessions} 日</dd></div>
      </dl>
      <p className="formula-identity">数据版本 · 更新至 {snapshot.date_range[1]}</p>
      <TechnicalDetails entries={[
        { label: "内容身份", value: snapshot.content_hash },
        { label: "数据快照身份", value: snapshot.data_snapshot_id },
      ]} />
      <button onClick={onClose} type="button">关闭公式抽屉</button>
    </aside>
  );
}

function FormulaStep({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}) {
  return <section><small>{label}</small>{children}</section>;
}
