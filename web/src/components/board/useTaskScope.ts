import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { TASK_SCOPE_PARAM, isAllWord, parseScope, readScope, rememberScope, scopeParam, type TaskScope } from "./taskScope";

const withScope = (current: URLSearchParams, value: string | null) => {
  const next = new URLSearchParams(current);
  if (value === null) next.delete(TASK_SCOPE_PARAM); else next.set(TASK_SCOPE_PARAM, value);
  return next;
};

// The Tasks area's selection (lead task 15). The address holds it; an address with none, as the Tasks area opens,
// takes the one this browser remembers and writes it in (replacing, so Back is not a step). From then on, no
// ?project= is All. Whatever is shown is remembered; ?project=all is All, and drops out of the address.
export function useTaskScope(): [TaskScope, (next: TaskScope) => void] {
  const [params, setParams] = useSearchParams();
  const raw = params.get(TASK_SCOPE_PARAM);
  const [restore, setRestore] = useState(() => (raw === null ? readScope() : null));
  const scope = parseScope(raw ?? restore);
  const value = scopeParam(scope);
  useEffect(() => {
    if (restore !== null && raw === null) {
      setParams((current) => withScope(current, restore), { replace: true });
    } else if (restore !== null) {
      setRestore(null); // the address holds it now (kept until then, so no render in between shows All)
    } else if (isAllWord(raw)) {
      setParams((current) => withScope(current, null), { replace: true });
    }
  }, [restore, raw, setParams]);
  useEffect(() => { if (restore === null) rememberScope(parseScope(value)); }, [restore, value]);
  const choose = useCallback((next: TaskScope) => setParams((current) => withScope(current, scopeParam(next))), [setParams]);
  return [scope, choose];
}
