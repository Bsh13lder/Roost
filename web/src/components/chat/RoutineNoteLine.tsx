import { parseNoteLine } from "../../lib/routineMessages";
import type { MessageOut } from "../../api/types";

// "Created routine · Digest" and "Picked: weekly · in your question book": one quiet line, like any activity.
export function RoutineNoteLine({ message }: { message: MessageOut }) {
  const line = parseNoteLine(message.body);
  if (!line) return null;
  return (
    <li className="message message--activity message--routine-note">
      <span className="message__activity-text">{line}</span>
    </li>
  );
}
