type RangeSelectorProps = {
  count: number;
  start: number;
  end: number;
  startLabel: string;
  endLabel: string;
  onChange: (start: number, end: number) => void;
};

export function RangeSelector({
  count,
  start,
  end,
  startLabel,
  endLabel,
  onChange,
}: RangeSelectorProps) {
  const maximum = Math.max(0, count - 1);
  const startPercent = maximum ? (start / maximum) * 100 : 0;
  const endPercent = maximum ? (end / maximum) * 100 : 100;

  return (
    <div className="range-block" data-testid="dual-range">
      <div className="range-labels">
        <span>{startLabel}</span>
        <span>{endLabel}</span>
      </div>
      <div className="range-track">
        <div
          className="range-selection"
          style={{ left: `${startPercent}%`, right: `${100 - endPercent}%` }}
        />
        <input
          aria-label="区间起点"
          type="range"
          min={0}
          max={maximum}
          value={start}
          onChange={(event) => onChange(Math.min(Number(event.target.value), end - 1), end)}
        />
        <input
          aria-label="区间终点"
          type="range"
          min={0}
          max={maximum}
          value={end}
          onChange={(event) => onChange(start, Math.max(Number(event.target.value), start + 1))}
        />
      </div>
    </div>
  );
}
