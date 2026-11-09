import { useCallback, useEffect, useRef, useState } from "react";
import * as questionsApi from "../api/questions";
import type { QuestionOut } from "../api/questions";
import { describeError } from "../api/client";
import { useLiveState } from "./useLiveStore";

// Every bot's open questions (My turn), reloaded on questions_changed. Only the newest load may answer.
export function useOpenQuestions() {
  const version = useLiveState().routineVersion?.questions;
  const [questions, setQuestions] = useState<readonly QuestionOut[]>([]);
  const [error, setError] = useState<string | null>(null);
  const latest = useRef(0);
  const reload = useCallback(() => {
    const ticket = ++latest.current;
    questionsApi.listQuestions()
      .then((loaded) => { if (ticket === latest.current) { setQuestions(loaded); setError(null); } })
      .catch((err: unknown) => { if (ticket === latest.current) setError(describeError(err)); });
  }, []);
  useEffect(() => reload(), [reload, version]);
  return { questions, error, reload };
}
