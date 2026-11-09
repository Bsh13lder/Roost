import { BOT_LIMITS } from "../lib/botProfile";
import { INSTRUCTIONS_COUNTER_FROM, characterCount, instructionsOver } from "../lib/botFields";

// Shown only near the limit; over it, it says what to do (the draft is never sent).
export function InstructionsCount({ text }: { text: string }) {
  const length = characterCount(text);
  if (length < INSTRUCTIONS_COUNTER_FROM) return null;
  const over = instructionsOver(text);
  return (
    <p className={`instructions-count${over > 0 ? " instructions-count--over" : ""}`} aria-live="polite">
      {over > 0 ? `${over} characters over the limit — shorten it to save.` : `${length} / ${BOT_LIMITS.instructions}`}
    </p>
  );
}
