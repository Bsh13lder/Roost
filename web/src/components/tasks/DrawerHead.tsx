import { useEffect, useRef, useState, type RefObject } from "react";
import { WebContentChip } from "../board/WebContentChip";
import { FromLazyClawMark } from "../board/FromLazyClawMark";
import { PriorityMark } from "../board/PriorityMark";
import { dueTone } from "../board/taskChips";
import { MAX_TITLE } from "../board/taskLimits";
import { dueWords } from "./TaskProps";
import { useLatest } from "./autosave";
import { useLiveState } from "../../hooks/useLiveStore";
import type { ProjectOut, TaskDetailOut } from "../../api/types";
import { Badge } from "../../ui/Badge";
import { useToast } from "../../ui/Toast";
import { cx } from "../../ui/cx";
import { todayIn } from "../../ui/date/dates";

export interface DrawerHeadProps {
  task: TaskDetailOut;
  project: ProjectOut | undefined;
  completing: boolean;
  onComplete: () => void;
  onTitle: (title: string) => Promise<boolean>; // saves a new title (a PATCH of `title`); true once saved
  onTitleLeave: (title: string) => void; // sends a title still being typed as the page goes away (pagehide)
  onKeep: () => void;
}

const OPEN: ReadonlySet<TaskDetailOut["status"]> = new Set(["todo", "in_progress"]);

const EMPTY_TITLE_HINT = "A task needs a title, so the old one is back.";

// The title is the head's own text field: no border until hover or focus. Enter or leaving it saves (and so
// does closing the drawer while it is being typed), Escape puts the old title back, and an empty title is
// never sent. A title that failed to save stays in the field until it saves.
function TitleField({ title, onTitle, onLeave }: { title: string; onTitle: (title: string) => Promise<boolean>; onLeave: (title: string) => void }) {
  const toast = useToast();
  const [text, setText] = useState(title);
  const field = useRef<HTMLInputElement>(null);
  const reverting = useRef(false);
  const editing = useRef(false);
  const held = useRef<string | null>(null); // a title sent but not saved yet
  const latest = useLatest({ text, title, onTitle, onLeave });
  useEffect(() => {
    if (editing.current || (held.current !== null && held.current !== title)) return;
    held.current = null;
    setText(title);
  }, [title]);
  useEscapeReverts(field, () => { reverting.current = true; setText(title); });
  const send = (next: string, save: (title: string) => Promise<boolean>) => {
    held.current = next;
    void save(next).then((saved) => { if (saved && held.current === next) held.current = null; });
  };
  useEffect(() => { // the drawer goes away (unmount) or the page does (pagehide) while the title is typed: save it
    const typedTitle = () => {
      const { text: typed, title: was } = latest.current;
      return editing.current && typed.trim() && typed.trim() !== was ? typed.trim() : null;
    };
    const onPageHide = () => { const next = typedTitle(); if (next) latest.current.onLeave(next); };
    window.addEventListener("pagehide", onPageHide);
    return () => {
      window.removeEventListener("pagehide", onPageHide);
      const next = typedTitle();
      if (next) void latest.current.onTitle(next);
    };
  }, [latest]);
  const leave = () => {
    editing.current = false;
    const next = text.trim();
    if (reverting.current || next === title) { reverting.current = false; setText(title); return; }
    if (!next) { setText(title); toast.show(EMPTY_TITLE_HINT); return; }
    send(next, onTitle);
  };
  return (
    <input ref={field} className="drawer-title" aria-label="Title" value={text} maxLength={MAX_TITLE} onFocus={() => { editing.current = true; }}
      onChange={(e) => setText(e.target.value)} onBlur={leave}
      onKeyDown={(e) => { if (e.key === "Enter") e.currentTarget.blur(); }} />
  );
}

// Escape in the title reverts it and must not close the drawer: the sheet listens on the document, so this
// listens first, on the window, and marks the key as handled.
function useEscapeReverts(field: RefObject<HTMLInputElement | null>, revert: () => void) {
  const latest = useLatest(revert);
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== "Escape" || event.target !== field.current) return;
      event.preventDefault();
      latest.current();
      field.current?.blur();
    };
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, [field]);
}

// The due in words, toned: danger when late, ok for today.
function DueCrumb({ due }: { due: string | null }) {
  const words = dueWords(due);
  if (!words) return null;
  const tone = dueTone(due, todayIn());
  return <Badge tone={tone === "over" ? "danger" : tone === "today" ? "ok" : "neutral"}>{words}</Badge>;
}

export function DrawerHead({ task, project, completing, onComplete, onTitle, onTitleLeave, onKeep }: DrawerHeadProps) {
  const { bots } = useLiveState();
  const maker = task.created_by_bot ? bots[task.created_by_bot]?.name ?? "a bot" : "you";
  return (
    <>
      <div className="drawer-head">
        <button type="button" className={cx("check", task.status === "done" && "is-done")} aria-label="Complete"
          aria-pressed={task.status === "done"} disabled={!OPEN.has(task.status) || completing} onClick={onComplete} />
        <TitleField title={task.title} onTitle={onTitle} onLeave={onTitleLeave} />
      </div>
      <div className="drawer-crumbs">
        {project ? <Badge><span className="dot" style={{ background: project.color }} aria-hidden="true" />{project.name}</Badge> : null}
        <DueCrumb due={task.due_date} />
        <PriorityMark priority={task.priority} size="pill" />
        <Badge>Made by {maker}</Badge>
        {task.tainted ? <WebContentChip what={task.title} onKeep={onKeep} /> : null}
        <FromLazyClawMark from={task.imported_from} />
      </div>
    </>
  );
}
