import { useEffect, useState, type RefObject } from "react";

// Whether the element is on screen, through an IntersectionObserver. A browser without one says no, so
// whatever waits on it (a live preview) stays closed rather than opening off screen.
export function useOnScreen(target: RefObject<Element | null>, enabled = true): boolean {
  const [onScreen, setOnScreen] = useState(false);
  useEffect(() => {
    const element = target.current;
    if (!enabled || !element || typeof IntersectionObserver === "undefined") {
      setOnScreen(false);
      return;
    }
    const observer = new IntersectionObserver((entries) => {
      const last = entries[entries.length - 1];
      if (last) setOnScreen(last.isIntersecting);
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, [target, enabled]);
  return onScreen;
}
