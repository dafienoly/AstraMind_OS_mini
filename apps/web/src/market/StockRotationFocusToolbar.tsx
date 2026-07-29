export function StockRotationFocusToolbar({
  zoom,
  trailLength,
  onZoom,
  onFit,
  onCenter,
  onTrailLength,
  onCollapse,
}: {
  zoom: number;
  trailLength: number;
  onZoom: (change: number) => void;
  onFit: () => void;
  onCenter: () => void;
  onTrailLength: (length: number) => void;
  onCollapse: () => void;
}) {
  return <div className="stock-rotation-focus-toolbar" aria-label="象限图显示控制">
    <div className="stock-rotation-tool-group">
      <span>视图</span>
      <button aria-label="缩小象限图" onClick={() => onZoom(-0.35)} type="button">−</button>
      <output aria-label="当前缩放">{Math.round(zoom * 100)}%</output>
      <button aria-label="放大象限图" onClick={() => onZoom(0.35)} type="button">＋</button>
      <button onClick={onFit} type="button">适配全部</button>
      <button onClick={onCenter} type="button">中心 100</button>
    </div>
    <fieldset>
      <legend>尾迹</legend>
      {[5, 10].map((length) => (
        <button
          aria-pressed={trailLength === length}
          key={length}
          onClick={() => onTrailLength(length)}
          type="button"
        >
          {length} 日
        </button>
      ))}
    </fieldset>
    <span className="stock-rotation-label-status">名称 · 全部常驻</span>
    <button className="stock-rotation-collapse" onClick={onCollapse} type="button">
      收起
    </button>
  </div>;
}
