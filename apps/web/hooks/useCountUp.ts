"use client";

import { useEffect, useRef, useState } from "react";

/**
 * Animates a numeric value smoothly toward its latest target whenever it
 * changes, used so dashboard stat cards don't just "jump" to a new number
 * every 5-second poll.
 */
export function useCountUp(value: number, durationMs = 600): number {
  const [display, setDisplay] = useState(value);
  const previousValue = useRef(value);
  const frameRef = useRef<number | undefined>(undefined);

  useEffect(() => {
    const start = previousValue.current;
    const end = value;

    if (start === end) return;

    const startTime = performance.now();

    function tick(now: number) {
      const progress = Math.min((now - startTime) / durationMs, 1);
      const eased = 1 - Math.pow(1 - progress, 3); // ease-out-cubic
      setDisplay(Math.round(start + (end - start) * eased));

      if (progress < 1) {
        frameRef.current = requestAnimationFrame(tick);
      } else {
        previousValue.current = end;
      }
    }

    frameRef.current = requestAnimationFrame(tick);

    return () => {
      if (frameRef.current) cancelAnimationFrame(frameRef.current);
    };
  }, [value, durationMs]);

  return display;
}
