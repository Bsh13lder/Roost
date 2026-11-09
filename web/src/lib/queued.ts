// web/src/lib/queued.ts — which of your sends are still waiting for a busy bot.
import type { MessageOut } from "../api/types";

// A queued id stays only while no bot message written after it comes later in the thread. A reply that was
// already being written when you sent (its bubble was made before your message) does not count: the bot
// picks your message up after that one.
export function stillQueued(messages: readonly MessageOut[], queuedIds: ReadonlySet<string>): ReadonlySet<string> {
  const kept = new Set<string>();
  for (const id of queuedIds) {
    const index = messages.findIndex((message) => message.id === id);
    if (index < 0) continue;
    const sentAt = Date.parse(messages[index].created_at);
    const answered = messages.slice(index + 1).some(
      (message) => message.role === "bot" && !(Date.parse(message.created_at) < sentAt),
    );
    if (!answered) kept.add(id);
  }
  return kept;
}
