import { useLayoutEffect, useState, type RefObject } from "react";
import { fitHeight } from "../ui/Textarea";

// Is the box taller than one row of text?
function holdsManyRows(box: HTMLTextAreaElement): boolean {
  const style = window.getComputedStyle(box);
  const line = Number.parseFloat(style.lineHeight) || Number.parseFloat(style.fontSize) * 1.5 || 20;
  const padding = (Number.parseFloat(style.paddingTop) || 0) + (Number.parseFloat(style.paddingBottom) || 0);
  return box.scrollHeight > line + padding + 1;
}

// Grows a textarea with its text in every browser (redesign P2): the kit's fitHeight after each change,
// up to maxRows lines, then it scrolls. CSS `field-sizing: content` alone works in Chromium only.
// Returns whether the box now holds more than one row (the composer pill turns into a rounded box).
export function useAutoGrow(box: RefObject<HTMLTextAreaElement | null>, value: string, maxRows: number): boolean {
  const [grew, setGrew] = useState(false);
  useLayoutEffect(() => {
    if (!box.current) return;
    fitHeight(box.current, maxRows);
    setGrew(holdsManyRows(box.current));
  }, [box, value, maxRows]);
  return grew;
}
