import { useEffect, useState } from "react";

const QUERY = "(prefers-reduced-motion: reduce)";

// Avatar.tsx's only consumer: static poses instead of CSS keyframes when
// the OS says to reduce motion. Exposed as a hook (rather than inlined)
// so other animated UI can reuse it later without duplicating the
// matchMedia wiring.
export function usePrefersReducedMotion(): boolean {
  const [reduced, setReduced] = useState<boolean>(() => window.matchMedia(QUERY).matches);

  useEffect(() => {
    const mql = window.matchMedia(QUERY);
    const onChange = () => setReduced(mql.matches);
    mql.addEventListener("change", onChange);
    return () => mql.removeEventListener("change", onChange);
  }, []);

  return reduced;
}
