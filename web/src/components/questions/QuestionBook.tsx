import { useCallback, useEffect, useId, useRef, useState } from "react";
import { Badge } from "../../ui/Badge";
import { Button } from "../../ui/Button";
import { Input } from "../../ui/Input";
import { describeError } from "../../api/client";
import * as questionsApi from "../../api/questions";
import type { QuestionOut } from "../../api/questions";
import { useLiveState } from "../../hooks/useLiveStore";
import { ErrorNotice } from "../ErrorNotice";

function QuestionRow({ question, onGone }: { question: QuestionOut; onGone: (id: string) => void }) {
  const [answer, setAnswer] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const run = async (work: () => Promise<unknown>) => {
    setBusy(true);
    setError(null);
    try { await work(); onGone(question.id); } catch (err) { setError(describeError(err)); } finally { setBusy(false); }
  };
  return (
    <li className="question-row">
      <p className="question-row__text">{question.question}</p>
      <p className="question-row__default">Carrying on with: {question.default_choice}</p>
      {question.why ? <p className="question-row__why">{question.why}</p> : null}
      {question.tainted ? <Badge tone="danger">from web content</Badge> : null}
      <div className="question-row__answer">
        <Input controlSize="md" aria-label={`Your answer to: ${question.question}`} value={answer}
          onChange={(event) => setAnswer(event.target.value)} />
        <Button size="sm" variant="primary" disabled={busy || !answer.trim()}
          onClick={() => void run(() => questionsApi.answerQuestion(question.id, answer.trim()))}>Answer</Button>
        <Button size="sm" variant="ghost" disabled={busy} onClick={() => void run(() => questionsApi.dismissQuestion(question.id))}>Dismiss</Button>
      </div>
      {error ? <p className="question-row__error" role="alert">{error}</p> : null}
    </li>
  );
}

// "Questions" on the Info tab (under Routines): what the bot wondered while it worked alone, and the default it
// carried on with. Answer posts your answer as your own message; Dismiss closes it quietly.
export function QuestionBook({ botId }: { botId: string }) {
  const headId = useId();
  const version = useLiveState().routineVersion?.questions;
  const [questions, setQuestions] = useState<readonly QuestionOut[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const latest = useRef(0);
  const load = useCallback(() => {
    const ticket = ++latest.current;
    questionsApi.listQuestions(botId)
      .then((loaded) => { if (ticket === latest.current) { setQuestions(loaded); setError(null); } })
      .catch((err: unknown) => { if (ticket === latest.current) setError(describeError(err)); });
  }, [botId]);
  useEffect(() => load(), [load, version]);
  if (questions?.length === 0 && !error) return null;
  return (
    <section className="info-card question-book" aria-labelledby={headId}>
      <h3 className="routines__title" id={headId}>Questions</h3>
      <ul className="question-book__list">
        {(questions ?? []).map((q) => (
          <QuestionRow key={q.id} question={q} onGone={(id) => setQuestions((now) => (now ?? []).filter((one) => one.id !== id))} />
        ))}
      </ul>
      {error ? <ErrorNotice message={error} onRetry={load} /> : null}
    </section>
  );
}
