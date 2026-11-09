import { useEffect, useRef } from "react";
import { TASK_VIEW_KEYS } from "./constants";
import type { TaskRowOut } from "../../api/tasks";
import type { BoardView as TaskView } from "./constants";

export interface TaskKeysOptions {
  enabled: boolean; // only in the List layout
  rows: readonly TaskRowOut[]; // the rows as shown, flat
  cursor: number;
  setCursor: (index: number) => void;
  onDone: (task: TaskRowOut) => void;
  onTomorrow: (task: TaskRowOut) => void;
  onOpen: (id: string) => void;
  onView?: (view: TaskView) => void; // 1 to 5; a project page has no views
  focusSearch: () => void;
  focusQuick: () => void;
}

const TYPING = "input, select, textarea, [contenteditable]:not([contenteditable='false'])";
// A menu, popover or the drawer is open: its own keys come first (Escape closes the top one, Radix handles it).
const OVERLAY = "[role='dialog'], [role='menu'], [role='listbox']";

// The List's keys (G4): j/k move the cursor, x done, t tomorrow, Enter opens, / searches, q adds, 1-5 pick a view.
// One keydown listener on the document; it ignores typing in a field, held modifiers and open overlays.
export function useTaskKeys(options: TaskKeysOptions): void {
  const latest = useRef(options);
  latest.current = options;
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const now = latest.current;
      const target = event.target instanceof Element ? event.target : null;
      if (!now.enabled || event.metaKey || event.ctrlKey || event.altKey || event.defaultPrevented) return;
      if (target?.closest(TYPING) || document.querySelector(OVERLAY)) return;
      if (event.key === "Enter" && target?.closest("button, a")) return; // Enter on a button presses it
      if (handle(event.key, now)) event.preventDefault();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);
}

// True when the key was one of ours.
function handle(key: string, now: TaskKeysOptions): boolean {
  const task = now.rows[now.cursor];
  const last = now.rows.length - 1;
  if (key === "j") now.setCursor(Math.min(now.cursor + 1, Math.max(last, 0)));
  else if (key === "k") now.setCursor(Math.max(now.cursor - 1, 0));
  else if (key === "x" && task) now.onDone(task);
  else if (key === "t" && task) now.onTomorrow(task);
  else if (key === "Enter" && task) now.onOpen(task.id);
  else if (key === "/") now.focusSearch();
  else if (key === "q") now.focusQuick();
  else if (/^[1-5]$/.test(key) && now.onView) now.onView(TASK_VIEW_KEYS[Number(key) - 1]);
  else return false;
  return true;
}
