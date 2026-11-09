import { useEffect, useState } from "react";
import { getTaskCounts } from "../../../api/tasks";
import { useLiveState } from "../../../hooks/useLiveStore";
import { NO_PROJECT } from "../taskScope";

// The Inbox's number in the rail: the server's count of open tasks with no project (counts?project_id=none,
// `open`); again on every tasks_changed. A failed load leaves it off (null): the Inbox still works.
export function useInboxCount(): number | null {
  const version = useLiveState().boardVersion.tasks;
  const [count, setCount] = useState<number | null>(null);
  useEffect(() => {
    let current = true;
    getTaskCounts(NO_PROJECT)
      .then((counts) => { if (current) setCount(counts.open); })
      .catch(() => { if (current) setCount(null); });
    return () => { current = false; };
  }, [version]);
  return count;
}
