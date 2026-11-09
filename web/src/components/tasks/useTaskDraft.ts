import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AMOUNT_HELP, readAmount } from "../board/money";
import { formatEstimate } from "./quickChips";
import * as tasksApi from "../../api/tasks";
import { describeError } from "../../api/client";
import { fieldWords, undoAction, useLatest } from "./autosave";
import type { TaskOut } from "../../api/types";
import { useToast } from "../../ui/Toast";
import { wallText } from "../../ui/date/dates";

export const NO_PROJECT = "none"; // a Select option is never "" (ui/Select.tsx)
const REPEAT_HELP = "Repeats can be daily, weekdays, weekly, monthly or yearly.";
const ESTIMATE_HELP = "Write an estimate like ~45m or ~2h.";

// A field the user typed that can't be read: its message is meant to be shown as it is.
export class DraftProblem extends Error {}

// What the drawer's properties hold, as text the user can edit. Due is not here: the reschedule popover saves it.
export interface DraftFields {
  reminder: string;
  repeat: string;
  priority: TaskOut["priority"];
  project: string;
  list: string;
  estimate: string;
  slice: string;
}

export function draftOf(task: TaskOut): DraftFields {
  return {
    reminder: wallText(task.reminder_at), repeat: task.repeat_text ?? "", priority: task.priority,
    project: task.project_id ?? NO_PROJECT, list: task.category ?? "",
    estimate: task.estimate_minutes ? `~${formatEstimate(task.estimate_minutes)}` : "", slice: task.allocated_budget ?? "",
  };
}

// Two values are the same when they only differ by spaces at the ends: "Home " is still "Home".
const sameValue = (a: string, b: string) => a.trim() === b.trim();
const sameFields = (a: DraftFields, b: DraftFields) => (Object.keys(a) as Array<keyof DraftFields>).every((key) => sameValue(a[key], b[key]));

// The fields the server reads in words (a repeat, an estimate): one quick-line read, like the quick add's.
async function readWords(text: string): Promise<{ recurring: string | null; minutes: number | null; problem: string | null }> {
  const line = await tasksApi.parseQuickLine({ text });
  return { recurring: line.recurring, minutes: line.estimate_minutes, problem: line.repeat_problem };
}

// The changes that need no reading by the server: every field but a typed repeat or estimate (an emptied one
// clears it). A budget slice it can't read throws its help.
export function plainChangesOf(before: DraftFields, after: DraftFields): tasksApi.TaskPatchIn {
  const changed = (key: keyof DraftFields) => !sameValue(before[key], after[key]);
  const projectId = after.project === NO_PROJECT ? null : after.project;
  const slice = readAmount(after.slice);
  if (changed("slice") && slice === undefined) throw new DraftProblem(AMOUNT_HELP);
  return {
    ...(changed("list") ? { category: after.list.trim() || null } : {}),
    ...(changed("priority") ? { priority: after.priority } : {}),
    // A reminder you set reminds you then, with no advance reminder (Remind me, 2026-10-23).
    ...(changed("reminder") ? { reminder_at: after.reminder.trim() || null } : {}),
    ...(changed("reminder") && after.reminder.trim() ? { pre_reminders: [] } : {}),
    ...(changed("repeat") && !after.repeat.trim() ? { recurring: null } : {}),
    ...(changed("estimate") && !after.estimate.trim() ? { estimate_minutes: null } : {}),
    ...(changed("project") ? { project_id: projectId } : {}),
    // Any task takes a budget; one in no project counts it in General's currency (owner, 2026-10-26).
    ...(changed("slice") ? { allocated_budget: slice ?? null } : {}),
  };
}

// What the page can still send as it goes away (pagehide): the plain changes, or nothing when a slice can't be read.
export function leaveChangesOf(before: DraftFields, after: DraftFields): tasksApi.TaskPatchIn {
  try {
    return plainChangesOf(before, after);
  } catch {
    return {};
  }
}

// Only what changed goes out (trimmed; spaces alone are no change); an emptied field clears it. A repeat or an
// estimate is read by the server first; one it can't read throws its help, as does a budget slice.
export async function changesOf(before: DraftFields, after: DraftFields): Promise<tasksApi.TaskPatchIn> {
  const changed = (key: keyof DraftFields) => !sameValue(before[key], after[key]);
  const plain = plainChangesOf(before, after);
  const repeat = changed("repeat") && after.repeat.trim() ? await readWords(after.repeat.trim()) : null;
  if (repeat && (repeat.problem || !repeat.recurring)) throw new DraftProblem(repeat.problem ?? REPEAT_HELP);
  const estimateText = after.estimate.trim().replace(/^~?/, "~");
  const estimate = changed("estimate") && after.estimate.trim() ? await readWords(estimateText) : null;
  if (estimate && !estimate.minutes) throw new DraftProblem(ESTIMATE_HELP);
  return {
    ...plain,
    ...(repeat ? { recurring: repeat.recurring } : {}),
    ...(estimate ? { estimate_minutes: estimate.minutes } : {}),
  };
}

export interface TaskDraft {
  draft: DraftFields;
  dirty: boolean; // something typed is not saved yet
  saving: boolean;
  set: <K extends keyof DraftFields>(field: K, value: DraftFields[K]) => void; // typing: kept until commit
  pick: <K extends keyof DraftFields>(field: K, value: DraftFields[K]) => void; // a pick: set and saved at once
  commit: () => Promise<void>; // saves whatever changed; nothing changed sends nothing
}

const isEmpty = (patch: object) => Object.keys(patch).length === 0;

// After a save: the saved task is the new base, and a field typed again while it was saving keeps its text.
function merged(current: DraftFields, sent: DraftFields, saved: DraftFields): DraftFields {
  const keys = Object.keys(current) as Array<keyof DraftFields>;
  return Object.fromEntries(keys.map((key) => [key, current[key] === sent[key] ? saved[key] : current[key]])) as unknown as DraftFields;
}

// The drawer's properties, saved on their own (lead task 01): a pick saves at once, typing saves on commit
// (Enter, leaving the editor, closing the drawer). Saves run one after another, so a second commit sees the
// first one's result and never sends the same change twice. When the task changes elsewhere (a bot, another
// tab) and nothing here is waiting, the fields follow it. Leaving the drawer saves what is still typed.
export function useTaskDraft(task: TaskOut, onSaved: () => void): TaskDraft {
  const toast = useToast();
  const [base, setBase] = useState<DraftFields>(() => draftOf(task));
  const [draft, setDraft] = useState<DraftFields>(base);
  const [saving, setSaving] = useState(false);
  const fields = useRef({ base, draft });
  const latest = useLatest({ task, onSaved, toast });
  const dirty = !sameFields(base, draft);
  const adopt = useCallback((next: DraftFields, nextDraft: DraftFields) => {
    fields.current = { base: next, draft: nextDraft };
    setBase(next);
    setDraft(nextDraft);
  }, []);
  useEffect(() => {
    if (!sameFields(fields.current.base, fields.current.draft)) return;
    const next = draftOf(task);
    adopt(next, next);
    // Only a new version of the task resets the fields; typing never does.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [task.updated_at]);
  const commit = useCommit(fields, latest, adopt, setSaving);
  const set = useCallback(<K extends keyof DraftFields>(field: K, value: DraftFields[K]) => {
    const next = { ...fields.current.draft, [field]: value };
    fields.current = { ...fields.current, draft: next };
    setDraft(next);
  }, []);
  const pick = useCallback(<K extends keyof DraftFields>(field: K, value: DraftFields[K]) => {
    set(field, value);
    void commit();
  }, [commit, set]);
  useEffect(() => () => { void commit(); }, [commit]); // the drawer went away (closed, another page)
  useSaveOnLeave(fields, latest);
  return useMemo(() => ({ draft, dirty, saving, set, pick, commit }), [draft, dirty, saving, set, pick, commit]);
}

interface Latest { task: TaskOut; onSaved: () => void; toast: ReturnType<typeof useToast> }

// The tab closes (or the page reloads) while a field is typed: send what can go without the server's reading,
// silently, in a request that outlives the page (lead 01b). A typed repeat or estimate cannot, and is lost.
function useSaveOnLeave(fields: { current: { base: DraftFields; draft: DraftFields } }, latest: { current: Latest }) {
  useEffect(() => {
    const onLeave = () => {
      const patch = leaveChangesOf(fields.current.base, fields.current.draft);
      if (!isEmpty(patch)) tasksApi.updateTaskOnLeave(latest.current.task.id, patch);
    };
    window.addEventListener("pagehide", onLeave);
    return () => window.removeEventListener("pagehide", onLeave);
  }, [fields, latest]);
}

// Saves whatever changed, one save after another. A field it can't read says why and keeps the text; a
// failed request keeps the text too, and its toast offers Try again; a good one offers Undo.
function useCommit(fields: { current: { base: DraftFields; draft: DraftFields } }, latest: { current: Latest },
  adopt: (next: DraftFields, nextDraft: DraftFields) => void, setSaving: (on: boolean) => void): () => Promise<void> {
  const queue = useRef<Promise<void>>(Promise.resolve());
  const retry = useRef<() => void>(() => undefined);
  const saveOnce = useCallback(async (): Promise<void> => {
    const { base, draft: sent } = fields.current;
    const { task, onSaved, toast } = latest.current;
    let patch: tasksApi.TaskPatchIn;
    try {
      patch = await changesOf(base, sent);
    } catch (err) {
      toast.show(err instanceof DraftProblem ? err.message : describeError(err), { tone: "danger" });
      return;
    }
    if (isEmpty(patch)) return;
    setSaving(true);
    try {
      const saved = await tasksApi.updateTask(task.id, patch);
      const next = draftOf(saved);
      adopt(next, merged(fields.current.draft, sent, next));
      onSaved();
      toast.show(`Saved ${fieldWords(patch)}`, { action: undoAction(toast, task, patch, onSaved) });
    } catch (err) {
      toast.show(`Couldn't save ${fieldWords(patch)}: ${describeError(err)}`,
        { tone: "danger", action: { label: "Try again", run: () => retry.current() } });
    } finally {
      setSaving(false);
    }
  }, [adopt, fields, latest, setSaving]);
  const commit = useCallback(() => (queue.current = queue.current.then(saveOnce).catch(() => undefined)), [saveOnce]);
  useEffect(() => { retry.current = () => void commit(); }, [commit]);
  return commit;
}
