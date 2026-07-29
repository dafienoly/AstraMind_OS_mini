import type { RotationLabelPlacement } from "./rotationLabelLayout";

export function RotationLabelLeaders({
  placements,
  width,
  height,
}: {
  placements: RotationLabelPlacement[];
  width: number;
  height: number;
}) {
  return <svg
    aria-hidden="true"
    className="rotation-label-leaders"
    preserveAspectRatio="none"
    viewBox={`0 0 ${width} ${height}`}
  >
    {placements.filter((placement) => placement.rail).map((placement) => (
      <path
        className={placement.selected ? "is-selected" : ""}
        d={`M${placement.nodeX.toFixed(2)},${placement.nodeY.toFixed(2)} L${placement.anchorX.toFixed(2)},${placement.anchorY.toFixed(2)}`}
        key={placement.code}
      />
    ))}
  </svg>;
}
