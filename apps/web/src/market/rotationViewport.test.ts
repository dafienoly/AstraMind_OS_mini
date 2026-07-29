import { expect, test } from "vitest";

import {
  applyRotationViewport,
  DEFAULT_ROTATION_VIEWPORT,
  fitRotationViewport,
  panRotationViewport,
  zoomRotationViewport,
} from "./rotationViewport";

test("rotation viewport zooms around its center and stays within limits", () => {
  expect(applyRotationViewport({ x: 60, y: 40 }, {
    centerX: 50,
    centerY: 50,
    zoom: 2,
  })).toEqual({ x: 70, y: 30 });
  expect(zoomRotationViewport(DEFAULT_ROTATION_VIEWPORT, -2).zoom).toBe(1);
  expect(zoomRotationViewport(DEFAULT_ROTATION_VIEWPORT, 8).zoom).toBe(3.2);
});

test("rotation viewport fits clustered points and pans in screen direction", () => {
  const fitted = fitRotationViewport([{ x: 42, y: 48 }, { x: 58, y: 52 }]);
  expect(fitted.centerX).toBe(50);
  expect(fitted.centerY).toBe(50);
  expect(fitted.zoom).toBeGreaterThan(1);

  const panned = panRotationViewport(fitted, 100, 50, 1000, 500);
  expect(panned.centerX).toBeLessThan(fitted.centerX);
  expect(panned.centerY).toBeGreaterThan(fitted.centerY);
});
