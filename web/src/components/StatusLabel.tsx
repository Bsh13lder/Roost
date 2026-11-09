import type { BotStatus } from "../api/types";
import { SIGN_IN_WAIT, signInWaitHost } from "../lib/stuck";

// Contract vocabulary (spec 7.4) — never another product's noun for a
// bot's state.
export const STATUS_LABELS: Record<BotStatus, string> = {
  resting: "Resting",
  on_it: "On it",
  asking_you: "Asking you",
  stuck: "Stuck",
  off_duty: "Off duty",
};

// What a status shows: its tone (the colour class), its word and the activity beside it. A bot waiting on a
// Sign-in card is Stuck on the server but reads "Waiting for you to sign in" in a calm colour, with its host.
export type StatusTone = BotStatus | "sign_in";
export interface StatusWords { tone: StatusTone; word: string; activity: string | null }

export function statusWords(status: BotStatus, activity?: string | null): StatusWords {
  const host = signInWaitHost(status, activity);
  if (host !== null) return { tone: "sign_in", word: SIGN_IN_WAIT, activity: host || null };
  return { tone: status, word: STATUS_LABELS[status], activity: activity ?? null };
}

export interface StatusLabelProps {
  status: BotStatus;
  activity?: string | null;
}

// The text label Avatar always renders next to the SVG, plus the live
// activity line when one is present — also reusable on its own (e.g. a
// compact team-list row that doesn't need the full avatar glyph). The
// dot takes the status color (styles/tokens.css); the word is always
// there too, so color is never the only signal.
export function StatusLabel({ status, activity }: StatusLabelProps) {
  const words = statusWords(status, activity);
  return (
    <span className={`status-label status-label--${words.tone}`}>
      <span className="status-label__state">
        <span className="status-label__dot" aria-hidden="true" />
        <span className="status-label__text">{words.word}</span>
      </span>
      {words.activity ? <span className="status-label__activity">{words.activity}</span> : null}
    </span>
  );
}
