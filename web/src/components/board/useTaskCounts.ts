import { useEffect, useRef, useState } from "react";
import { ApiError } from "../../api/client";
import { getTaskCounts, type TaskCountsOut } from "../../api/tasks";
import { useLiveState } from "../../hooks/useLiveStore";

// The Board's tab counts: loaded once, and again whenever a task changes. `projectId` narrows them to one project,
// or to the tasks with none ("none"); a new selection shows no counts until its own arrive. A failed load leaves
// the counts off (null); the tabs still work. A project the server does not know (404) also calls `onGone`.
export function useTaskCounts(projectId?: string, onGone?: () => void): TaskCountsOut | null {
  const version = useLiveState().boardVersion.tasks;
  const key = projectId ?? "";
  const gone = useRef(onGone);
  gone.current = onGone;
  const [found, setFound] = useState<{ key: string; counts: TaskCountsOut | null } | null>(null);
  useEffect(() => {
    let current = true;
    getTaskCounts(key || undefined)
      .then((counts) => { if (current) setFound({ key, counts }); })
      .catch((err: unknown) => {
        if (!current) return;
        setFound({ key, counts: null });
        if (key && err instanceof ApiError && err.status === 404) gone.current?.();
      });
    return () => { current = false; };
  }, [version, key]);
  return found?.key === key ? found.counts : null;
}
