import { useCallback, useEffect, useRef } from "react";
import * as tasksApi from "../../api/tasks";
import { describeError } from "../../api/client";
import type { TaskOut } from "../../api/types";
import { useToast, type ToastApi } from "../../ui/Toast";
import { wallText } from "../../ui/date/dates";

// The task drawer saves each edit on its own (lead task 01): these are the words its toasts use, the Undo
// patch, and the title's save. Every save says so with Undo; a failed one says why and offers Try again.

type PatchKey = keyof tasksApi.TaskPatchIn;

const FIELD_WORDS: Partial<Record<PatchKey, string>> = {
  category: "list", priority: "priority", reminder_at: "reminder", recurring: "repeat",
  estimate_minutes: "estimate", project_id: "project", allocated_budget: "budget slice", title: "title",
};

const keysOf = (patch: tasksApi.TaskPatchIn) => Object.keys(patch) as PatchKey[];

// "the priority", "the project and budget slice".
export function fieldWords(patch: tasksApi.TaskPatchIn): string {
  const words = keysOf(patch).map((key) => FIELD_WORDS[key] ?? key);
  return `the ${words.join(" and ")}`;
}

// The patch that puts each changed field back as it was. A reminder goes back as account wall text, the way
// the drawer sends it; a project change also puts back the earlier budget slice.
export function undoPatch(patch: tasksApi.TaskPatchIn, was: TaskOut): tasksApi.TaskPatchIn {
  const back: Record<string, unknown> = {};
  for (const key of keysOf(patch)) {
    back[key] = key === "reminder_at" ? wallText(was.reminder_at) || null : was[key] ?? null;
  }
  if ("project_id" in patch && was.project_id !== null) back.allocated_budget = was.allocated_budget;
  return back as tasksApi.TaskPatchIn;
}

// Undo of one save: one PATCH back, then a reload; a failed Undo says why.
export function undoAction(toast: ToastApi, was: TaskOut, patch: tasksApi.TaskPatchIn, reload: () => void) {
  return {
    label: "Undo",
    run: () => {
      tasksApi.updateTask(was.id, undoPatch(patch, was)).then(reload)
        .catch((err: unknown) => toast.show(describeError(err), { tone: "danger" }));
    },
  };
}

// A ref that always holds the latest value: saves that finish after the drawer closed still reach it.
export function useLatest<T>(value: T) {
  const ref = useRef(value);
  useEffect(() => { ref.current = value; });
  return ref;
}

// The title's save: resolves true once saved. A failure keeps the typed title (the field holds it) and the
// toast's Try again sends it again.
export function useTitleSave(task: TaskOut, reload: () => void): (title: string) => Promise<boolean> {
  const toast = useToast();
  const latest = useLatest({ task, reload });
  const save = useCallback(async (title: string): Promise<boolean> => {
    const { task: was, reload: refresh } = latest.current;
    try {
      await tasksApi.updateTask(was.id, { title });
    } catch (err) {
      toast.show(`Couldn't save the title: ${describeError(err)}`,
        { tone: "danger", action: { label: "Try again", run: () => void save(title) } });
      return false;
    }
    refresh();
    toast.show(`Renamed to “${title}”`, { action: undoAction(toast, was, { title }, refresh) });
    return true;
  }, [latest, toast]);
  return save;
}
