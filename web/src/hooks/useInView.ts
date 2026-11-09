import { useEffect, useState, type RefObject } from "react";

// True while the element is on screen (IntersectionObserver). Where the browser has none (tests), it counts as seen.
export function useInView(ref: RefObject<Element | null>, margin = "120px"): boolean {
  const [seen, setSeen] = useState(() => typeof IntersectionObserver === "undefined");
  useEffect(() => {
    const element = ref.current;
    if (!element || typeof IntersectionObserver === "undefined") return undefined;
    const observer = new IntersectionObserver((entries) => {
      const entry = entries.at(-1);
      if (entry) setSeen(entry.isIntersecting);
    }, { rootMargin: margin });
    observer.observe(element);
    return () => observer.disconnect();
  }, [ref, margin]);
  return seen;
}
