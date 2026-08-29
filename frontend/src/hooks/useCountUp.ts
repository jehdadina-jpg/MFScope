import { useEffect, useRef, useState } from "react";

const EASE_OUT = (t: number) => 1 - Math.pow(1 - t, 3);

/**
 * Animates a number from 0 (or its previous value) to `target` using
 * requestAnimationFrame with a strong ease-out — the number arrives fast and
 * settles gently, matching every other motion in this app.
 *
 * Skips the animation entirely under `prefers-reduced-motion`.
 */
export function useCountUp(target: number | null | undefined, duration = 900): number | null {
  const [value, setValue] = useState<number | null>(target ?? null);
  const fromRef = useRef(0);
  const rafRef = useRef<number>();

  useEffect(() => {
    if (target == null) return;
    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduceMotion) {
      setValue(target);
      return;
    }

    const from = fromRef.current;
    const start = performance.now();

    function tick(now: number) {
      const elapsed = now - start;
      const t = Math.min(1, elapsed / duration);
      const eased = EASE_OUT(t);
      setValue(from + (target! - from) * eased);
      if (t < 1) {
        rafRef.current = requestAnimationFrame(tick);
      } else {
        fromRef.current = target!;
      }
    }

    rafRef.current = requestAnimationFrame(tick);
    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [target, duration]);

  return value;
}
