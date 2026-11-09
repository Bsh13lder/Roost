import { useCallback, useEffect, useState } from "react";
import * as projectsApi from "../../api/projects";
import { describeError } from "../../api/client";
import { useLiveState } from "../../hooks/useLiveStore";
import { isGeneral } from "../projects/projects";
import type { ProjectOut } from "../../api/types";

// The user's projects a task may belong to (redesign P3): every live one but General, archived ones
// included (a task may already be in one). Reloads on money_changed, which carries project changes (H10),
// on tasks_changed too with `followTasks` (the Tasks rail: each project's open count moves with its tasks),
// and on `reload` (the Tasks rail, after it made one). `enabled` false (a project's own page) asks for
// nothing. A failed load keeps the last list and says why (`error`, and the console): the rows lose their
// project chip, nothing else breaks. `loaded` is whether a list has ever come back.
export interface ProjectListState {
  projects: readonly ProjectOut[];
  loaded: boolean;
  error: string | null;
  reload: () => void;
}

export function useProjectList(enabled = true, followTasks = false): ProjectListState {
  const version = useLiveState().boardVersion;
  const tasks = followTasks ? version.tasks : 0;
  const [asked, setAsked] = useState(0);
  const [found, setFound] = useState<{ projects: readonly ProjectOut[]; loaded: boolean; error: string | null }>(
    { projects: [], loaded: false, error: null });
  useEffect(() => {
    if (!enabled) return undefined;
    let current = true;
    projectsApi.listProjects(true)
      .then((all) => { if (current) setFound({ projects: all.filter((project) => !isGeneral(project)), loaded: true, error: null }); })
      .catch((err: unknown) => {
        const error = describeError(err);
        console.warn("Could not load the projects:", error);
        if (current) setFound((last) => ({ ...last, error }));
      });
    return () => { current = false; };
  }, [enabled, version.money, tasks, asked]);
  const reload = useCallback(() => setAsked((count) => count + 1), []);
  return { ...found, reload };
}

export function useProjects(enabled = true): readonly ProjectOut[] {
  return useProjectList(enabled).projects;
}
