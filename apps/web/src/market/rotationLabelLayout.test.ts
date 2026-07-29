import { expect, test } from "vitest";

import {
  layoutRotationLabels,
  type RotationLabelPlacement,
} from "./rotationLabelLayout";

test("persistent label layout is deterministic and keeps every label in bounds", () => {
  const inputs = Array.from({ length: 60 }, (_, index) => ({
    code: `stock-${String(index).padStart(2, "0")}`,
    name: `合成股票${String(index).padStart(2, "0")}`,
    nodeX: 155 + index % 6 * 7,
    nodeY: 150 + Math.floor(index / 6) * 6,
    selected: index === 11,
    emphasized: index === 11,
    detailed: index === 11,
  }));
  const first = layoutRotationLabels(inputs, 350, 380);
  const second = layoutRotationLabels(inputs, 350, 380);

  expect(first).toEqual(second);
  expect(first).toHaveLength(inputs.length);
  expect(first.some((placement) => placement.rail)).toBe(true);
  expect(first.find((placement) => placement.selected)?.height).toBe(42);
  expect(first.every((placement) =>
    placement.labelX >= 8
    && placement.labelY >= 34
    && placement.labelX + placement.width <= 342
    && placement.labelY + placement.height <= 352)).toBe(true);
  expect(overlappingPairs(first)).toEqual([]);
  expect(first.map(({ code, nodeX, nodeY }) => ({ code, nodeX, nodeY })))
    .toEqual(inputs.map(({ code, nodeX, nodeY }) => ({ code, nodeX, nodeY })));
});

test("selected label keeps readable height in dense mode without detail rows", () => {
  const inputs = Array.from({ length: 31 }, (_, index) => ({
    code: `industry-${index}`,
    name: index === 0 ? "医药生物" : `行业${index}`,
    nodeX: 140 + index % 5,
    nodeY: 150 + index % 7,
    selected: index === 0,
    emphasized: index === 0,
    detailed: false,
  }));
  const selected = layoutRotationLabels(inputs, 800, 520)
    .find((placement) => placement.selected);

  expect(selected?.height).toBe(28);
  expect(selected?.width).toBeGreaterThanOrEqual(150);
});

function overlappingPairs(placements: RotationLabelPlacement[]) {
  const overlaps: string[] = [];
  for (let leftIndex = 0; leftIndex < placements.length; leftIndex += 1) {
    for (let rightIndex = leftIndex + 1; rightIndex < placements.length; rightIndex += 1) {
      const left = placements[leftIndex];
      const right = placements[rightIndex];
      if (
        left.labelX < right.labelX + right.width
        && left.labelX + left.width > right.labelX
        && left.labelY < right.labelY + right.height
        && left.labelY + left.height > right.labelY
      ) overlaps.push(`${left.code}:${right.code}`);
    }
  }
  return overlaps;
}
