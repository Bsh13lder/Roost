import type { MessageOut } from "../api/types";
import { REACTION_GLYPHS, type ReactionKey } from "../components/chat/constants";

export const isReactionMessage = (message: MessageOut): boolean => message.kind === "reaction";

const isKey = (value: unknown): value is ReactionKey => typeof value === "string" && value in REACTION_GLYPHS;

// Each message's tapback: the newest reaction row for it wins, and a null key clears it. A row whose body
// is not a tapback is ignored. Returns a new map; the messages are never changed.
export function foldReactions(messages: readonly MessageOut[]): ReadonlyMap<string, ReactionKey> {
  const folded = new Map<string, ReactionKey>();
  for (const message of messages) {
    if (!isReactionMessage(message)) continue;
    try {
      const { target_id: target, key } = JSON.parse(message.body) as { target_id?: unknown; key?: unknown };
      if (typeof target !== "string") continue;
      if (key === null) folded.delete(target);
      else if (isKey(key)) folded.set(target, key);
    } catch {
      continue; // not JSON: no tapback
    }
  }
  return folded;
}
