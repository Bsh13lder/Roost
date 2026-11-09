import { useCallback, useEffect, useRef, useState } from "react";
import * as connectorsApi from "../api/connectors";
import type { KeyRequestOut } from "../api/connectors";
import { describeError } from "../api/client";
import { useLiveState } from "./useLiveStore";

// The open Add a key cards (Connectors), reloaded on connector_requests_changed. Only the newest load may answer.
export function useOpenKeyRequests() {
  const version = useLiveState().connectorVersion;
  const [requests, setRequests] = useState<readonly KeyRequestOut[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const latest = useRef(0);
  const reload = useCallback(() => {
    const ticket = ++latest.current;
    connectorsApi.listKeyRequests()
      .then((loaded) => { if (ticket === latest.current) { setRequests(loaded); setError(null); } })
      .catch((err: unknown) => { if (ticket === latest.current) setError(describeError(err)); });
  }, []);
  useEffect(() => reload(), [reload, version]);
  return { requests, error, reload };
}
