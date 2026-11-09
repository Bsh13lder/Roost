import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { MessageList } from "../components/MessageList";
import { ErrorNotice } from "../components/ErrorNotice";
import { describeError } from "../api/client";
import * as routinesApi from "../api/routines";
import type { RoutineOut } from "../api/routines";
import * as threadsApi from "../api/threads";
import type { MessageOut } from "../api/types";
import { useLiveState } from "../hooks/useLiveStore";
import { mergeMessages } from "../lib/messages";

type Loaded = { routine: RoutineOut; messages: MessageOut[] } | "missing" | null;

// A routine's run log (routines plan): the thread its runs happen in, read-only. There is no composer: you talk
// to the bot in its chat, and every run leaves its instructions, its steps and its Report here.
export function RoutineLog() {
  const { botId = "", routineId = "" } = useParams<{ botId: string; routineId: string }>();
  const live = useLiveState();
  const [loaded, setLoaded] = useState<Loaded>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let current = true;
    routinesApi.listRoutines(botId)
      .then(async (routines) => {
        const routine = routines.find((one) => one.id === routineId);
        if (!routine) return "missing" as const;
        return { routine, messages: await threadsApi.listMessages(routine.thread_id) };
      })
      .then((result) => { if (current) setLoaded(result); })
      .catch((err: unknown) => { if (current) setError(describeError(err)); });
    return () => { current = false; };
  }, [botId, routineId]);

  const bot = live.bots[botId];
  const back = <Link className="routine-log__back" to={`/bots/${botId}`}>Back to the chat</Link>;
  if (error) return <div className="routine-log">{back}<ErrorNotice message={error} /></div>;
  if (loaded === null) return <p className="page-loading">Loading&hellip;</p>;
  if (loaded === "missing") return <div className="routine-log">{back}<p>{"That routine isn't here any more."}</p></div>;
  const title = loaded.routine.builtin ? "End-of-day summary" : loaded.routine.name;
  const messages = mergeMessages(loaded.messages, live.messagesByThread[loaded.routine.thread_id] ?? []);
  return (
    <div className="routine-log">
      <header className="routine-log__head">
        {back}
        <h2 className="routine-log__title">{title} · run log</h2>
      </header>
      <MessageList messages={messages} streaming={live.streaming} botName={bot?.name ?? "Bot"} botAvatar={bot?.avatar}
        team={bot ? [bot] : []} />
    </div>
  );
}
