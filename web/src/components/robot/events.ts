// Live frames become robot events (avatars v5 "Statuses and events", kept in v7). Pure: the frame, the state it
// arrives on (before it is applied) and the open chat in, the events out. hooks/useRobotEvents.ts
// feeds them to the avatars.
import type { ServerFrame } from "../../api/types";
import type { LiveState } from "../../store/live";
import type { RobotEvent } from "./moments";

export interface RobotEventFor {
  readonly botId: string;
  readonly name: RobotEvent;
}

// A step that makes a record, as the gateway announces it ("adding a task", "logging an expense",
// "saving a note", "writing a doc", "creating a project", "making a sheet", "filing a document").
export const CREATING_VERBS: readonly string[] = ["adding", "creating", "making", "filing", "logging", "saving", "writing"];

const creates = (activity: string | null | undefined): boolean =>
  CREATING_VERBS.includes((activity ?? "").trim().split(" ")[0].toLowerCase());

function statusEvents(frame: Extract<ServerFrame, { type: "bot_status" }>, state: LiveState): RobotEventFor[] {
  const before = state.bots[frame.bot_id];
  if (!before) return [];
  const found: RobotEventFor[] = [];
  // A creating step ends: the next step begins, or the bot settles. The record exists.
  if (before.status === "on_it" && creates(before.activity) && (frame.activity !== before.activity || frame.status !== "on_it")) {
    found.push({ botId: frame.bot_id, name: "created" });
  }
  if (frame.status === "stuck" && before.status !== "stuck") found.push({ botId: frame.bot_id, name: "stuck" });
  return found;
}

export function robotEventsFor(frame: ServerFrame, state: LiveState, openBotId: string | null): readonly RobotEventFor[] {
  switch (frame.type) {
    case "bot_status":
      return statusEvents(frame, state);
    case "message_done": {
      const closed = (state.messagesByThread[frame.thread_id] ?? []).find((message) => message.id === frame.message_id);
      return closed?.author_bot_id ? [{ botId: closed.author_bot_id, name: "done" }] : [];
    }
    case "message": {
      const { message } = frame;
      const reply = message.role === "bot" && (message.kind ?? "text") === "text" && message.seq > 0 && message.body.trim() !== "";
      if (!reply || !message.author_bot_id || message.author_bot_id === openBotId) return [];
      return [{ botId: message.author_bot_id, name: "msg" }];
    }
    default:
      return [];
  }
}

/** Every bot with a reply started (its placeholder, seq 0) and no text streamed for it yet. */
export function thinkingBots(state: LiveState): ReadonlySet<string> {
  const found = new Set<string>();
  for (const messages of Object.values(state.messagesByThread)) {
    for (const message of messages) {
      if (message.seq === 0 && message.role === "bot" && message.author_bot_id && !(state.streaming[message.id] ?? "")) {
        found.add(message.author_bot_id);
      }
    }
  }
  return found;
}
