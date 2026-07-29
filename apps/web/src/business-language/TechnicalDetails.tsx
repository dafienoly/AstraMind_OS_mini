export interface TechnicalDetail {
  label: string;
  value: string | readonly string[] | null | undefined;
}

export function TechnicalDetails({
  entries,
  summary = "技术详情",
}: {
  entries: readonly TechnicalDetail[];
  summary?: string;
}) {
  const visible = entries.filter((entry) => (
    Array.isArray(entry.value) ? entry.value.length > 0 : Boolean(entry.value)
  ));
  if (!visible.length) return null;
  return <details aria-label="技术详情">
    <summary>{summary}</summary>
    <p>以下原始值仅用于诊断，不代表业务结论。</p>
    <dl>
      {visible.map((entry) => <div key={entry.label}>
        <dt>{entry.label}</dt>
        <dd><code>{Array.isArray(entry.value) ? entry.value.join(" · ") : entry.value}</code></dd>
      </div>)}
    </dl>
  </details>;
}
