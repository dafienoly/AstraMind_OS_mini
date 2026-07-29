export interface RotationLabelInput {
  code: string;
  name: string;
  nodeX: number;
  nodeY: number;
  selected: boolean;
  emphasized: boolean;
  detailed: boolean;
}

export interface RotationLabelPlacement extends RotationLabelInput {
  labelX: number;
  labelY: number;
  width: number;
  height: number;
  anchorX: number;
  anchorY: number;
  rail: boolean;
}

interface Box {
  x: number;
  y: number;
  width: number;
  height: number;
}

export function layoutRotationLabels(
  inputs: RotationLabelInput[],
  plotWidth: number,
  plotHeight: number,
): RotationLabelPlacement[] {
  const dense = inputs.length > 30;
  const bounds = {
    left: 8,
    top: 34,
    right: Math.max(80, plotWidth - 8),
    bottom: Math.max(80, plotHeight - 28),
  };
  const occupied: Box[] = [];
  const placements = [...inputs]
    .sort((left, right) =>
      Number(right.selected) - Number(left.selected) || left.code.localeCompare(right.code))
    .map((input) => {
      const size = labelSize(input, dense, plotWidth);
      const nearby = nearbyCandidates(input, size);
      const box = nearby.find((candidate) =>
        isAvailable(candidate, occupied, bounds));
      const placed = box ?? railPlacement(input, size, occupied, bounds);
      occupied.push(placed);
      return toPlacement(input, placed, box == null);
    });
  return placements.sort((left, right) => left.code.localeCompare(right.code));
}

function labelSize(input: RotationLabelInput, dense: boolean, plotWidth: number) {
  const units = Array.from(input.name).reduce(
    (total, character) => total + (character.charCodeAt(0) <= 0xff ? 0.62 : 1),
    0,
  );
  const width = input.detailed
    ? Math.min(plotWidth - 20, Math.max(138, units * 10 + 88))
    : Math.min(
      plotWidth - 20,
      Math.max(42, units * (dense ? 8 : 9) + (input.emphasized ? 120 : 12)),
    );
  const height = input.detailed ? 42 : input.emphasized ? 28 : dense ? 16 : 20;
  return { width, height };
}

function nearbyCandidates(input: RotationLabelInput, size: { width: number; height: number }) {
  const { nodeX: x, nodeY: y } = input;
  const { width, height } = size;
  const gap = 11;
  return [
    { x: x + gap, y: y - height / 2, width, height },
    { x: x - width - gap, y: y - height / 2, width, height },
    { x: x + gap, y: y - height - gap, width, height },
    { x: x - width - gap, y: y - height - gap, width, height },
    { x: x + gap, y: y + gap, width, height },
    { x: x - width - gap, y: y + gap, width, height },
    { x: x - width / 2, y: y - height - gap, width, height },
    { x: x - width / 2, y: y + gap, width, height },
  ];
}

function railPlacement(
  input: RotationLabelInput,
  size: { width: number; height: number },
  occupied: Box[],
  bounds: { left: number; top: number; right: number; bottom: number },
) {
  const leftColumns = [bounds.left, bounds.left + size.width + 4];
  const rightColumns = [
    bounds.right - size.width,
    bounds.right - size.width * 2 - 4,
  ];
  const columns = input.nodeX < (bounds.left + bounds.right) / 2
    ? [...leftColumns, ...rightColumns]
    : [...rightColumns, ...leftColumns];
  const rows = [];
  for (let y = bounds.top; y <= bounds.bottom - size.height; y += size.height + 3) {
    rows.push(y);
  }
  rows.sort((left, right) =>
    Math.abs(left - input.nodeY) - Math.abs(right - input.nodeY) || left - right);
  for (const x of columns) {
    for (const y of rows) {
      const candidate = { x, y, ...size };
      if (isAvailable(candidate, occupied, bounds)) return candidate;
    }
  }
  return gridPlacement(size, occupied, bounds);
}

function gridPlacement(
  size: { width: number; height: number },
  occupied: Box[],
  bounds: { left: number; top: number; right: number; bottom: number },
) {
  for (let y = bounds.top; y <= bounds.bottom - size.height; y += size.height + 2) {
    for (let x = bounds.left; x <= bounds.right - size.width; x += 6) {
      const candidate = { x, y, ...size };
      if (isAvailable(candidate, occupied, bounds)) return candidate;
    }
  }
  return { x: bounds.left, y: bounds.top, ...size };
}

function isAvailable(
  candidate: Box,
  occupied: Box[],
  bounds: { left: number; top: number; right: number; bottom: number },
) {
  if (
    candidate.x < bounds.left || candidate.y < bounds.top
    || candidate.x + candidate.width > bounds.right
    || candidate.y + candidate.height > bounds.bottom
  ) return false;
  return occupied.every((box) =>
    candidate.x + candidate.width + 3 <= box.x
    || box.x + box.width + 3 <= candidate.x
    || candidate.y + candidate.height + 3 <= box.y
    || box.y + box.height + 3 <= candidate.y);
}

function toPlacement(input: RotationLabelInput, box: Box, rail: boolean) {
  return {
    ...input,
    labelX: box.x,
    labelY: box.y,
    width: box.width,
    height: box.height,
    anchorX: Math.max(box.x, Math.min(input.nodeX, box.x + box.width)),
    anchorY: Math.max(box.y, Math.min(input.nodeY, box.y + box.height)),
    rail,
  };
}
