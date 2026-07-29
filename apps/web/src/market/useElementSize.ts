import { useLayoutEffect, useRef, useState } from "react";

export function useElementSize(defaultWidth = 800, defaultHeight = 520) {
  const ref = useRef<HTMLElement | null>(null);
  const [size, setSize] = useState({ width: defaultWidth, height: defaultHeight });
  useLayoutEffect(() => {
    const element = ref.current;
    if (!element) return;
    const update = () => {
      const bounds = element.getBoundingClientRect();
      if (bounds.width > 0 && bounds.height > 0) {
        setSize((current) => (
          current.width === bounds.width && current.height === bounds.height
            ? current
            : { width: bounds.width, height: bounds.height }
        ));
      }
    };
    update();
    if (typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(update);
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  return { ref, ...size };
}
