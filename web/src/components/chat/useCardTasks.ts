import { useCallback, useEffect, useState } from "react";
import { listTasks, type TaskRowOut } from "../../api/tasks";
import { describeError } from "../../api/client";
import { useLiveState } from "../../hooks/useLiveStore";

export interface CardTasks {
  tasks: readonly TaskRowOut[] | null; // null until the first answer
  error: string | null;
  reload: () => void;
}

// The tasks a chat card shows, fetched by id (GET /api/tasks?ids=, in the order asked; a deleted task is simply not
// there), and fetched again whenever a tasks_changed frame arrives, so a tick anywhere shows here too.
export function useCardTasks(ids: readonly string[]): CardTasks {
  const version = useLiveState().boardVersion.tasks;
  const [asked, setAsked] = useState(0);
  const [state, setState] = useState<{ tasks: readonly TaskRowOut[] | null; error: string | null }>(
    { tasks: null, error: null });
  const key = ids.join(",");
  useEffect(() => {
    if (!key) return undefined;
    let current = true;
    listTasks({ ids: key.split(",") })
      .then((tasks) => { if (current) setState({ tasks, error: null }); })
      .catch((err: unknown) => { if (current) setState((last) => ({ ...last, error: describeError(err) })); });
    return () => { current = false; };
  }, [key, version, asked]);
  const reload = useCallback(() => setAsked((count) => count + 1), []);
  return { ...state, reload };
}
