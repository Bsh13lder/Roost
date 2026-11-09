import { useEffect, useState } from "react";
import * as tasksApi from "../../api/tasks";
import { describeError } from "../../api/client";
import { useLiveState } from "../../hooks/useLiveStore";

/** The tags the user's tasks already carry (for "#" autocomplete), most used first. Reloads when tasks
 * change; asks for nothing until `enabled`. A failed load leaves the list empty and says why in the console. */
export function useTags(enabled: boolean): readonly string[] {
  const version = useLiveState().boardVersion.tasks;
  const [tags, setTags] = useState<readonly string[]>([]);
  useEffect(() => {
    if (!enabled) return undefined;
    let current = true;
    tasksApi.listTasks("all")
      .then((tasks) => { if (current) setTags(rankedTags(tasks.flatMap((task) => task.tags ?? []))); })
      .catch((err: unknown) => console.warn("Could not load the tags:", describeError(err)));
    return () => { current = false; };
  }, [enabled, version]);
  return tags;
}

/** Each tag once (first spelling wins), the most used first. */
export function rankedTags(all: readonly string[]): readonly string[] {
  const counts = new Map<string, { name: string; count: number }>();
  for (const name of all) {
    const key = name.toLocaleLowerCase();
    const seen = counts.get(key);
    counts.set(key, { name: seen?.name ?? name, count: (seen?.count ?? 0) + 1 });
  }
  return [...counts.values()].sort((a, b) => b.count - a.count || a.name.localeCompare(b.name)).map((tag) => tag.name);
}
