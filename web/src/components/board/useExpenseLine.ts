import { useEffect, useRef, useState } from "react";
import { QUICK_PARSE_DELAY_MS } from "../tasks/constants";
import * as moneyApi from "../../api/money";
import { describeError } from "../../api/client";
import type { ExpenseKind, ExpenseLineOut } from "../../api/money";

export interface ExpenseLineReading {
  line: ExpenseLineOut | null; // the server's reading of the latest text, null for none (or no text)
  error: string | null;
}

/** What the server would add for this line: asked QUICK_PARSE_DELAY_MS after the last key, and only the
 * newest answer counts, so a slow reply never draws chips for text that has changed. */
export function useExpenseLine(text: string, projectId: string | undefined, skip: readonly ExpenseKind[],
  defaultDay?: string): ExpenseLineReading {
  const [reading, setReading] = useState<ExpenseLineReading>({ line: null, error: null });
  const latest = useRef(0);
  const skipKey = skip.join(",");
  useEffect(() => {
    const ticket = ++latest.current;
    if (!text.trim()) {
      setReading({ line: null, error: null });
      return undefined;
    }
    const timer = window.setTimeout(() => {
      const input = { text, ...(projectId ? { project_id: projectId } : {}), ...(skip.length ? { skip: [...skip] } : {}),
        ...(defaultDay ? { default_day: defaultDay } : {}) };
      moneyApi.parseExpenseLine(input)
        .then((line) => { if (ticket === latest.current) setReading({ line, error: null }); })
        .catch((err: unknown) => { if (ticket === latest.current) setReading({ line: null, error: describeError(err) }); });
    }, QUICK_PARSE_DELAY_MS);
    return () => window.clearTimeout(timer);
    // skipKey stands for skip: a new array with the same kinds asks nothing new.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [text, projectId, skipKey, defaultDay]);
  return reading;
}
