import { useEffect, useRef, useState } from "react";
import { QUICK_PARSE_DELAY_MS } from "./constants";
import * as tasksApi from "../../api/tasks";
import { describeError } from "../../api/client";
import type { QuickKindRich, QuickLineRichOut } from "../../api/tasks";

export interface QuickLineReading {
  line: QuickLineRichOut | null; // the server's reading of the latest text, null for none (or no text)
  error: string | null;
}

/** What the server would add for this line (redesign P3): asked QUICK_PARSE_DELAY_MS after the last key,
 * and only the newest answer counts, so a slow reply never draws chips for text that has changed. */
export function useQuickLine(
  text: string, projectId: string | undefined, skip: readonly QuickKindRich[], keep: readonly string[] = [],
  defaultDue?: string,
): QuickLineReading {
  const [reading, setReading] = useState<QuickLineReading>({ line: null, error: null });
  const latest = useRef(0);
  const skipKey = `${skip.join(",")}|${keep.join("\u0001")}`;
  useEffect(() => {
    const ticket = ++latest.current;
    if (!text.trim()) {
      setReading({ line: null, error: null });
      return undefined;
    }
    const timer = window.setTimeout(() => {
      const input = { text, ...(projectId ? { project_id: projectId } : {}), ...(skip.length ? { skip: [...skip] } : {}),
        ...(keep.length ? { keep: [...keep] } : {}), ...(defaultDue ? { default_due: defaultDue } : {}) };
      tasksApi.parseQuickLine(input)
        .then((line) => { if (ticket === latest.current) setReading({ line, error: null }); })
        .catch((err: unknown) => { if (ticket === latest.current) setReading({ line: null, error: describeError(err) }); });
    }, QUICK_PARSE_DELAY_MS);
    return () => window.clearTimeout(timer);
    // skipKey stands for skip and keep: a new array with the same kinds asks nothing new.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [text, projectId, skipKey, defaultDue]);
  return reading;
}
