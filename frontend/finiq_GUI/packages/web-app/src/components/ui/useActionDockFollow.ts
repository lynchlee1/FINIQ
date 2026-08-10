"use client";

import { useCallback, useEffect, useState } from "react";

const DESKTOP_QUERY = "(min-width: 768px)";
const REDUCED_MOTION_QUERY = "(prefers-reduced-motion: reduce)";
const VIEWPORT_INSET = 24;

export function useActionDockFollow<T extends HTMLElement = HTMLDivElement>() {
  const [dock, setDock] = useState<T | null>(null);
  const dockRef = useCallback((node: T | null) => setDock(node), []);

  useEffect(() => {
    const host = dock?.closest<HTMLElement>(".action-dock-host");
    if (!dock || !host) return;

    const desktop = window.matchMedia(DESKTOP_QUERY);
    const reducedMotion = window.matchMedia(REDUCED_MOTION_QUERY);
    let frame = 0;
    let current = 0;
    let target = 0;
    let velocity = 0;
    let maxTravel = 0;

    const render = () => {
      dock.style.transform = `translate3d(0, ${current}px, 0)`;
    };

    const clampCurrent = () => {
      const boundedCurrent = Math.min(maxTravel, Math.max(0, current));
      if (boundedCurrent === current) return false;
      current = boundedCurrent;
      velocity = 0;
      return true;
    };

    const animate = () => {
      const distance = target - current;
      velocity = (velocity + distance * 0.12) * 0.72;
      current += velocity;
      clampCurrent();

      if (Math.abs(distance) < 0.1 && Math.abs(velocity) < 0.1) {
        current = target;
        velocity = 0;
        frame = 0;
        render();
        return;
      }

      render();
      frame = window.requestAnimationFrame(animate);
    };

    const updateTarget = () => {
      if (!desktop.matches) {
        if (frame) window.cancelAnimationFrame(frame);
        frame = 0;
        current = 0;
        target = 0;
        velocity = 0;
        dock.style.transform = "";
        return;
      }

      const hostTop = host.getBoundingClientRect().top;
      maxTravel = Math.max(0, host.scrollHeight - dock.offsetHeight);
      target = Math.min(maxTravel, Math.max(0, VIEWPORT_INSET - hostTop));
      if (clampCurrent()) render();

      if (reducedMotion.matches) {
        if (frame) window.cancelAnimationFrame(frame);
        frame = 0;
        current = target;
        velocity = 0;
        render();
        return;
      }

      if (!frame) frame = window.requestAnimationFrame(animate);
    };

    window.addEventListener("scroll", updateTarget, { passive: true });
    window.addEventListener("resize", updateTarget);
    desktop.addEventListener("change", updateTarget);
    reducedMotion.addEventListener("change", updateTarget);
    const resizeObserver = new ResizeObserver(updateTarget);
    resizeObserver.observe(host);
    resizeObserver.observe(dock);
    updateTarget();

    return () => {
      if (frame) window.cancelAnimationFrame(frame);
      window.removeEventListener("scroll", updateTarget);
      window.removeEventListener("resize", updateTarget);
      desktop.removeEventListener("change", updateTarget);
      reducedMotion.removeEventListener("change", updateTarget);
      resizeObserver.disconnect();
      dock.style.transform = "";
    };
  }, [dock]);

  return dockRef;
}
