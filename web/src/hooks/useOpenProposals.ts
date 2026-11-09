import { useCallback, useEffect, useRef, useState } from "react";
import * as proposalsApi from "../api/proposals";
import type { ProposalOut } from "../api/proposals";
import { describeError } from "../api/client";
import { useLiveState } from "./useLiveStore";

// The user's open routine proposals, reloaded on proposals_changed. Only the newest load may answer.
export function useOpenProposals() {
  const version = useLiveState().routineVersion?.proposals;
  const [proposals, setProposals] = useState<readonly ProposalOut[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const latest = useRef(0);
  const reload = useCallback(() => {
    const ticket = ++latest.current;
    proposalsApi.listProposals()
      .then((loaded) => { if (ticket === latest.current) { setProposals(loaded); setError(null); } })
      .catch((err: unknown) => { if (ticket === latest.current) setError(describeError(err)); });
  }, []);
  useEffect(() => reload(), [reload, version]);
  return { proposals, error, reload };
}
