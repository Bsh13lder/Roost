import { useCallback, useState } from "react";
import { applyAccent, readAccent, saveAccent, type AccentId } from "../lib/accent";

// The accent colour as state: a pick applies at once and is remembered in this browser (main.tsx applies the saved
// one before the first paint).
export function useAccent(): [AccentId, (id: AccentId) => void] {
  const [accent, setAccent] = useState<AccentId>(readAccent);
  const choose = useCallback((id: AccentId) => {
    applyAccent(id);
    saveAccent(id);
    setAccent(id);
  }, []);
  return [accent, choose];
}
