import { useCallback, useEffect, useRef, useState } from "react";
import * as skillsApi from "../api/skills";
import type { SkillProposalOut } from "../api/skills";
import { describeError } from "../api/client";
import { useLiveState } from "./useLiveStore";

// The user's open skill proposals (Skills), reloaded on skill_proposals_changed. Only the newest load may answer.
export function useOpenSkillProposals() {
  const version = useLiveState().skillVersion?.proposals;
  const [proposals, setProposals] = useState<readonly SkillProposalOut[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const latest = useRef(0);
  const reload = useCallback(() => {
    const ticket = ++latest.current;
    skillsApi.listSkillProposals()
      .then((loaded) => { if (ticket === latest.current) { setProposals(loaded); setError(null); } })
      .catch((err: unknown) => { if (ticket === latest.current) setError(describeError(err)); });
  }, []);
  useEffect(() => reload(), [reload, version]);
  return { proposals, error, reload };
}
