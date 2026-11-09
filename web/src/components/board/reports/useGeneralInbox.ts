import { useCallback, useEffect, useRef, useState } from "react";
import * as moneyApi from "../../../api/money";
import { describeError } from "../../../api/client";
import type { RangeExpenseOut } from "../../../api/money";

// The expenses sitting in General, newest first (GET /api/money/general), a page at a time. Reloads when money
// changes (`version`); `more` fetches the next page and adds it below.
export function useGeneralInbox(version: number) {
  const [expenses, setExpenses] = useState<readonly RangeExpenseOut[]>([]);
  const [next, setNext] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const latest = useRef(0);
  const reload = useCallback(() => {
    const ticket = ++latest.current;
    moneyApi.getGeneralInbox()
      .then((page) => { if (ticket === latest.current) { setExpenses(page.expenses); setNext(page.next); setError(null); } })
      .catch((err: unknown) => { if (ticket === latest.current) setError(describeError(err)); });
  }, []);
  useEffect(() => reload(), [reload, version]);
  const more = useCallback(() => {
    if (next === null) return;
    const ticket = ++latest.current;
    moneyApi.getGeneralInbox(next)
      .then((page) => { if (ticket === latest.current) { setExpenses((now) => [...now, ...page.expenses]); setNext(page.next); } })
      .catch((err: unknown) => { if (ticket === latest.current) setError(describeError(err)); });
  }, [next]);
  return { expenses, hasMore: next !== null, error, reload, more };
}
