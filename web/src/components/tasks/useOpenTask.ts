import { useCallback } from "react";
import { useSearchParams } from "react-router-dom";
import { TASK_PARAM } from "./constants";

// The task whose drawer is open, kept in the address (?task=<id>, redesign P3) beside the Board's own
// ?tab=, so a reload or a link opens the same drawer. Closing removes it without a history entry.
export function useOpenTask(): { openId: string | null; open: (taskId: string) => void; close: () => void } {
  const [params, setParams] = useSearchParams();
  const open = useCallback((taskId: string) => {
    setParams((current) => {
      const next = new URLSearchParams(current);
      next.set(TASK_PARAM, taskId);
      return next;
    });
  }, [setParams]);
  const close = useCallback(() => {
    setParams((current) => {
      const next = new URLSearchParams(current);
      next.delete(TASK_PARAM);
      return next;
    }, { replace: true });
  }, [setParams]);
  return { openId: params.get(TASK_PARAM), open, close };
}
