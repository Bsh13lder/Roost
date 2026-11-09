import { useEffect, useRef, type CSSProperties } from "react";
import type { ApprovalCardOut, BotOut, MessageOut, StuckCardOut } from "../../api/types";
import { usePrefersReducedMotion } from "../../hooks/usePrefersReducedMotion";
import type { SpeechReady } from "../../store/live";
import { englishFixFor } from "../../lib/englishFix";
import { Avatar } from "../Avatar";
import { EnglishFixText } from "../chat/EnglishFixRow";
import { HangUpIcon, MicIcon, MicOffIcon } from "../icons";
import { useCall, type CallPhase, type CallView } from "./useCall";

export interface CallScreenProps {
  bot: BotOut;
  threadId: string;
  messages: readonly MessageOut[];
  approvals: readonly ApprovalCardOut[];
  stuck: readonly StuckCardOut[];
  streaming: Readonly<Record<string, string>>; // the live store's text as the reply streams (the caption)
  speechReady: Readonly<Record<string, SpeechReady>>; // the live store's speech_ready frames
  onSend: (text: string, options: { call: true; spoken: true }) => Promise<string>; // your message's id
  onClose: () => void;
}

const PHASE_WORDS: Record<Exclude<CallPhase, "failed">, string> = {
  warming: "Warming up…",
  listening: "Listening",
  hearing: "Hearing you…",
  thinking: "Thinking…",
  speaking: "Speaking",
};

// The line under the bot's name: Muted in every phase, the bot's own words while it works, else the phase.
export function statusWords(call: CallView, bot: BotOut): string {
  if (call.phase === "failed") return call.error ?? "";
  if (call.muted) return "Muted";
  if (call.phase === "thinking" && bot.activity) return bot.activity;
  return PHASE_WORDS[call.phase];
}

function orbLabel(call: CallView, bot: BotOut): string {
  if (call.phase === "speaking") return "Stop speaking";
  if (call.phase === "listening" && !call.muted) return "Send now";
  return statusWords(call, bot);
}

const AVATAR_SIZE = 112;
const SHOWS_REPLY: ReadonlySet<CallPhase> = new Set(["thinking", "speaking"]);

// A call with a bot (voice call mode): full screen over the chat. You talk, it answers aloud; every turn also lands in
// the chat as your own message and its reply. The orb sends now while listening and stops the bot while it speaks;
// Space stops it too; Escape or End leaves.
export default function CallScreen({ bot, threadId, messages, approvals, stuck, streaming, speechReady, onSend, onClose }: CallScreenProps) {
  const call = useCall({ bot, threadId, messages, approvals, stuck, streaming, speechReady, send: onSend, onClose });
  const reduced = usePrefersReducedMotion();
  const endRef = useRef<HTMLButtonElement>(null);
  const close = useRef(onClose);
  close.current = onClose;
  const interrupt = useRef(call.interrupt);
  interrupt.current = call.interrupt;

  useEffect(() => { endRef.current?.focus(); }, []);
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") close.current();
      if (event.key === " ") {
        event.preventDefault(); // never a click on the focused End or Mute
        if (!event.repeat) interrupt.current();
      }
    };
    const onKeyUp = (event: KeyboardEvent) => { if (event.key === " ") event.preventDefault(); };
    document.addEventListener("keydown", onKey);
    document.addEventListener("keyup", onKeyUp);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("keyup", onKeyUp);
    };
  }, []);

  const orbStyle = { "--call-level": call.level } as CSSProperties;
  // Correct my English: the newest english_fix line for this turn takes the place of the plain words you said.
  const fix = call.heardId ? englishFixFor(messages, call.heardId) : null;
  return (
    <div className="call" role="dialog" aria-modal="true" aria-label={`Call with ${bot.name}`}
      data-reduced-motion={reduced ? "true" : undefined}>
      <div className="call__who">
        <Avatar avatar={bot.avatar} status={bot.status} size={AVATAR_SIZE} label={false} decorative star={bot.is_primary}
          botId={bot.id} />
        <h2 className="call__name">{bot.name}</h2>
        <p className="call__status" data-testid="call-status" role="status"
          data-failed={call.phase === "failed" ? "true" : undefined}>{statusWords(call, bot)}</p>
      </div>
      <button type="button" className="call__orb" data-testid="call-orb" data-phase={call.phase}
        data-muted={call.muted ? "true" : undefined} style={orbStyle} onClick={call.orbTap}
        disabled={call.phase === "failed"} aria-label={orbLabel(call, bot)}>
        <span className="call__orb-core" aria-hidden="true" />
      </button>
      <div className="call__caption" aria-live="polite">
        {fix ? <div className="call__fix"><EnglishFixText fix={fix} /></div>
          : call.heard ? <p className="call__heard">{call.heard}</p> : null}
        {call.reply && SHOWS_REPLY.has(call.phase) ? <p className="call__reply">{call.reply}</p> : null}
        {call.note ? <p className="call__note">{call.note}</p> : null}
      </div>
      <div className="call__controls">
        <button type="button" className="call__button" aria-pressed={call.muted} onClick={call.toggleMute}
          disabled={call.phase === "failed"} aria-label={call.muted ? "Unmute" : "Mute"}>
          {call.muted ? <MicOffIcon /> : <MicIcon />}
        </button>
        <button type="button" ref={endRef} className="call__button call__button--end" onClick={onClose} aria-label="End call">
          <HangUpIcon />
        </button>
      </div>
    </div>
  );
}
