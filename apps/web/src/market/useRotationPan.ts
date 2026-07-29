import { useRef } from "react";
import type { PointerEventHandler } from "react";

import { panRotationViewport } from "./rotationViewport";
import type { RotationViewport } from "./rotationViewport";

export function useRotationPan(
  viewport: RotationViewport,
  onViewportChange: ((viewport: RotationViewport) => void) | undefined,
  onClear: () => void,
) {
  const drag = useRef<{
    pointerId: number;
    x: number;
    y: number;
    viewport: RotationViewport;
  } | null>(null);
  const suppressClick = useRef(false);
  const onPointerDown: PointerEventHandler<HTMLElement> = (event) => {
    if (!onViewportChange || (event.target as Element).closest("button")) return;
    drag.current = { pointerId: event.pointerId, x: event.clientX, y: event.clientY, viewport };
    event.currentTarget.setPointerCapture(event.pointerId);
  };
  const onPointerMove: PointerEventHandler<HTMLElement> = (event) => {
    const start = drag.current;
    if (!start || start.pointerId !== event.pointerId || !onViewportChange) return;
    const deltaX = event.clientX - start.x;
    const deltaY = event.clientY - start.y;
    if (Math.hypot(deltaX, deltaY) > 3) suppressClick.current = true;
    const bounds = event.currentTarget.getBoundingClientRect();
    onViewportChange(panRotationViewport(
      start.viewport,
      deltaX,
      deltaY,
      bounds.width,
      bounds.height,
    ));
  };
  const onPointerEnd: PointerEventHandler<HTMLElement> = (event) => {
    if (drag.current?.pointerId !== event.pointerId) return;
    event.currentTarget.releasePointerCapture(event.pointerId);
    drag.current = null;
  };
  const onClick = () => {
    if (suppressClick.current) {
      suppressClick.current = false;
      return;
    }
    onClear();
  };
  return { onClick, onPointerCancel: onPointerEnd, onPointerDown, onPointerMove, onPointerUp: onPointerEnd };
}
