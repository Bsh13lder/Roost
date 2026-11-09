import { useCallback, useState } from "react";
import * as tasksApi from "../../api/tasks";
import { describeError } from "../../api/client";
import type { PastedListOut } from "../../api/tasks";
import { taskInputOf } from "./quickChips";

const LINE_BREAK = /\r?\n/;

/** True when pasted text holds more than one non-empty line: a list, not a task. */
export function isPastedList(text: string): boolean {
  return text.split(LINE_BREAK).filter((row) => row.trim()).length > 1;
}

export interface PastedList {
  list: PastedListOut | null; // the server's reading, waiting for your yes
  busy: boolean;
  error: string | null;
  read: (text: string) => Promise<void>;
  cancel: () => void;
  confirm: () => Promise<boolean>; // creates every task; false when one failed (the rest stay to retry)
}

/** A pasted list (Amendment T): read by the server, confirmed by you, then created one task at a time. */
export function usePastedList(projectId: string | undefined, onAdded: () => void): PastedList {
  const [list, setList] = useState<PastedListOut | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const read = useCallback(async (text: string) => {
    setBusy(true);
    setError(null);
    try {
      setList(await tasksApi.parsePastedList({ text, ...(projectId ? { project_id: projectId } : {}) }));
    } catch (err) {
      setList(null);
      setError(describeError(err));
    } finally {
      setBusy(false);
    }
  }, [projectId]);
  const cancel = useCallback(() => { setList(null); setError(null); }, []);
  const confirm = useCallback(async () => {
    if (!list || !list.ready) return false;
    setBusy(true);
    setError(null);
    let left = list.tasks;
    try {
      while (left.length) {
        await tasksApi.createTask(taskInputOf(left[0]));
        left = left.slice(1);
      }
      setList(null);
      onAdded();
      return true;
    } catch (err) {
      setList({ ...list, tasks: left, count: left.length });
      setError(describeError(err));
      if (left.length !== list.tasks.length) onAdded();
      return false;
    } finally {
      setBusy(false);
    }
  }, [list, onAdded]);
  return { list, busy, error, read, cancel, confirm };
}
