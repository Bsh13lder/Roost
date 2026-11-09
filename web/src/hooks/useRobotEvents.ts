import { useEffect, useRef, useSyncExternalStore } from "react";
import { robotEventsFor, thinkingBots, type RobotEventFor } from "../components/robot/events";
import type { RobotEventIn } from "../components/robot/moments";
import { onLiveFrame, subscribeLive } from "./useLiveStore";

// The ghosts' live events (avatars v5): one small store beside the live store. `useRobotEventFeed`
// (mounted once, in Layout) turns every incoming frame into keyed events and keeps the set of bots
// whose run has started with no text yet; each Avatar reads its own bot's through `useBotEvent` and
// `useBotThinking`, so a frame re-renders only the avatars it touches.
let events: Readonly<Record<string, RobotEventIn>> = {};
let thinking: ReadonlySet<string> = new Set();
let nextKey = 0;
const listeners = new Set<() => void>();
const notify = () => listeners.forEach((listener) => listener());

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function publishRobotEvents(found: readonly RobotEventFor[]): void {
  if (found.length === 0) return;
  const next = { ...events };
  for (const { botId, name } of found) {
    nextKey += 1;
    next[botId] = { name, key: nextKey };
  }
  events = next;
  notify();
}

const sameSet = (a: ReadonlySet<string>, b: ReadonlySet<string>) => a.size === b.size && [...a].every((id) => b.has(id));

export function setThinkingBots(next: ReadonlySet<string>): void {
  if (sameSet(thinking, next)) return;
  thinking = next;
  notify();
}

export function resetRobotEventsForTests(): void {
  events = {};
  thinking = new Set();
  nextKey = 0;
}

const NO_EVENT = null;

export function useBotEvent(botId: string | undefined): RobotEventIn | null {
  return useSyncExternalStore(subscribe, () => (botId ? events[botId] ?? NO_EVENT : NO_EVENT));
}

export function useBotThinking(botId: string | undefined): boolean {
  return useSyncExternalStore(subscribe, () => (botId ? thinking.has(botId) : false));
}

/** Mounted once: feeds the store from the live frames. `openBotId` is the chat on screen (its replies are not "new"). */
export function useRobotEventFeed(openBotId: string | null): void {
  const open = useRef(openBotId);
  open.current = openBotId;
  useEffect(() => {
    const stopFrames = onLiveFrame((frame, state) => publishRobotEvents(robotEventsFor(frame, state, open.current)));
    const stopState = subscribeLive((state) => setThinkingBots(thinkingBots(state)));
    return () => { stopFrames(); stopState(); };
  }, []);
}
