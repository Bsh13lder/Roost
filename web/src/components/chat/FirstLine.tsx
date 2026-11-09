import type { AvatarOut } from "../../api/types";
import { WorkingTimer } from "../WorkingIndicator";
import { FIRST_LINE_DEFAULT_ACTIVITY } from "./constants";
import { WorkingBot } from "./WorkingBot";

export interface FirstLineProps {
  text: string; // what has streamed so far
  activity: string | null; // what the bot says it is doing
  since: number; // when the bubble began (epoch ms)
  name?: string; // the bot, for the screen-reader label
  avatar?: AvatarOut; // its robot, which works beside the words
}

// "reading your message" → "Reading your message…"
export function workingWords(activity: string | null): string {
  const words = (activity || FIRST_LINE_DEFAULT_ACTIVITY).trim().replace(/[.…]+$/, "");
  return `${words.charAt(0).toUpperCase()}${words.slice(1)}…`;
}

// A reply's first moment: the streamed words when there are any; else the bot's own robot at work (its eyes act
// out what it does) with what it is doing in words and how long it has been at it (owner, 2026-10-27: no more
// "On it" text). UI only, never stored.
export function FirstLine({ text, activity, since, name = "The bot", avatar }: FirstLineProps) {
  if (text) return <div className="message__body message__body--streaming" aria-busy="true">{text}</div>;
  const words = workingWords(activity);
  return (
    <div className="message__typing" role="status" aria-label={`${name}: ${words}`}>
      <WorkingBot avatar={avatar} kind="think" />
      <span className="message__first-line">{words}</span>
      <WorkingTimer since={since} />
    </div>
  );
}
