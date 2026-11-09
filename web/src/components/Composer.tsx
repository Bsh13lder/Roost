import { useId, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import { COMPOSER_MAX_ROWS } from "./chat/constants";
import { useMentionPicker } from "./chat/useMentionPicker";
import { MentionList } from "./MentionList";
import type { MentionOption } from "../lib/mentions";
import type { EnglishFix } from "../api/types";
import { useAutoGrow } from "../hooks/useAutoGrow";
import type { SpokenCorrection } from "../hooks/useMicRecorder";
import { isSendKey } from "../lib/composerKeys";
import { MicButton } from "./chat/MicButton";
import { CallButton } from "./chat/CallButton";
import { SpokenFixStrip } from "./chat/SpokenFixStrip";
import { reprobeVoiceInfo } from "../lib/voiceInfo";

// What a send says about its words: `spoken` when they came from the voice service and were not edited after the
// transcription landed (Correct what I say reads such a message). Once the composer checked them (voice tuning D3),
// `heard` is the raw transcript and `fixes` what was marked, so the server keeps the marks with no second check.
export interface SendMeta {
  readonly spoken: boolean;
  readonly heard?: string;
  readonly fixes?: readonly EnglishFix[];
}

export interface ComposerProps {
  onSend: (text: string, meta: SendMeta) => void | Promise<void>;
  placeholder?: string;
  disabled?: boolean;
  // "large" is the roomier box; "regular" the docked one. Purely visual.
  size?: "regular" | "large";
  // Drawn inside the pill before the text box: the chat's round + (polish R1.12).
  leading?: ReactNode;
  // Your other bots: typing "@" lists them, and the server hands the message to the ones you name.
  mentions?: readonly MentionOption[];
  // Your projects: typing "#" lists them, and the server tells the bot which project "#Name" means.
  projects?: readonly MentionOption[];
  // Voice: a mic beside Send (hidden when the Mac's voice service is off); what you say lands in the box (the words
  // show as you speak), and a failure is said through onError. With the bot and its Correct what I say switch,
  // the cleaned words take their place with the fixes marked above the box.
  voice?: { onError: (message: string) => void; botId?: string; correct?: boolean };
  // Call mode: while the box is empty the round Send becomes Call (when voice runs and this browser can record).
  call?: { name: string; onCall: () => void };
  // Pictures wait to go (owner, 2026-11-05): Send works with no words.
  allowEmpty?: boolean;
}

// What you said joins what is already typed, after a space.
export function withSpokenText(typed: string, spoken: string): string {
  const kept = typed.replace(/\s+$/, "");
  return kept ? `${kept} ${spoken}` : spoken;
}

// The box holds a transcription nobody has edited: what was typed before it, what the ear heard, the whole box
// as it landed (`heard`), whether the check came back, and the fixes shown now.
interface Spoken {
  readonly before: string;
  readonly said: string;
  readonly heard: string;
  readonly checked: boolean;
  readonly fixes: readonly EnglishFix[];
}

function sendMeta(spoken: Spoken | null): SendMeta {
  if (!spoken) return { spoken: false };
  return spoken.checked ? { spoken: true, heard: spoken.heard, fixes: spoken.fixes } : { spoken: true };
}

// Enter sends, Shift+Enter inserts a newline (never the Enter an IME uses), and the box grows with its text.
export function Composer({
  onSend, placeholder, disabled = false, size = "regular", leading, mentions, projects, voice, call, allowEmpty = false,
}: ComposerProps) {
  const [text, setTextState] = useState("");
  const [live, setLive] = useState(""); // the words so far while the mic records (voice tuning D4)
  const [spoken, setSpokenState] = useState<Spoken | null>(null);
  const [correction, setCorrection] = useState<SpokenCorrection | null>(null);
  const [sending, setSending] = useState(false);
  const boxRef = useRef<HTMLTextAreaElement>(null);
  // The box's text and the spoken bookkeeping, written at once: the mic's callbacks fire from fetches and timers,
  // often before React has drawn the last change, so they read these and never a render's copy.
  const textRef = useRef("");
  const spokenRef = useRef<Spoken | null>(null);
  const setText = (value: string) => { textRef.current = value; setTextState(value); };
  const setSpoken = (value: Spoken | null) => { spokenRef.current = value; setSpokenState(value); };
  const shown = live ? withSpokenText(text, live) : text;
  const many = useAutoGrow(boxRef, shown, COMPOSER_MAX_ROWS);
  // A picked @bot or #project edits the text too: the message is typed from then on.
  const picker = useMentionPicker(boxRef, text, (value) => { setText(value); setSpoken(null); setCorrection(null); }, mentions, projects);
  const listId = useId();
  const listOpen = picker.shown.length > 0;

  const trySend = () => {
    const trimmed = text.trim();
    if (trimmed.length === 0 && !allowEmpty) return;
    const result = onSend(trimmed, sendMeta(spoken));
    const clear = () => { setText(""); setSpoken(null); setCorrection(null); };
    if (result && typeof result.then === "function") {
      // Only clear the box once the send actually succeeds — a failed
      // send (dropped connection, momentary 5xx) must leave the typed
      // text in place instead of forcing the user to retype it from
      // memory. The caller (e.g. the chat's onSend) is responsible for
      // surfacing the error itself; disabling input meanwhile avoids a
      // double-send race while this one is still pending.
      setSending(true);
      result
        .then(clear)
        .catch(() => {
          // Intentionally swallowed here — the caller already recorded
          // the error. This handler only decides whether the box clears.
        })
        .finally(() => setSending(false));
    } else {
      clear();
    }
  };

  // The ear's final words: they join what was typed, and the box holds a transcription from now on.
  const onSpoken = (words: string) => {
    const typed = textRef.current;
    const heard = withSpokenText(typed, words);
    setLive("");
    setCorrection(null);
    setSpoken({ before: typed, said: words, heard, checked: false, fixes: [] });
    setText(heard);
    boxRef.current?.focus();
  };

  // The check came back (voice tuning D3): the cleaned words take the raw ones' place while nobody edited them.
  const onCorrected = (found: SpokenCorrection) => {
    const current = spokenRef.current;
    if (!current || textRef.current !== current.heard) return;
    setText(withSpokenText(current.before, found.corrected));
    setCorrection(found);
    setSpoken({ ...current, checked: true, fixes: found.fixes });
  };
  const onChecked = () => {
    const current = spokenRef.current;
    if (current) setSpoken({ ...current, checked: true });
  };
  const onKeep = () => {
    const current = spokenRef.current;
    if (!current) return;
    setText(current.heard);
    setSpoken({ ...current, fixes: [] });
    setCorrection(null);
  };

  // Any edit of the box's text, a keystroke or a paste, makes the message typed.
  const onEdit = (value: string, caret: number) => {
    if (live) return; // the live words are the ear's, not yours to edit yet
    setText(value);
    setSpoken(null);
    setCorrection(null);
    picker.onEdit(caret);
  };

  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (picker.onKeyDown(event)) return;
    if (isSendKey(event)) {
      event.preventDefault();
      if (!live) trySend();
    }
  };

  const sendButton = (
    <button
      type="button"
      className="composer__send"
      onClick={trySend}
      disabled={disabled || sending || Boolean(live) || (text.trim().length === 0 && !allowEmpty)}
    >
      <svg className="composer__send-icon" viewBox="0 0 20 20" width={18} height={18} aria-hidden="true" focusable="false">
        <path d="M10 16V4M4.5 9.5 10 4l5.5 5.5" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" />
      </svg>
      <span className="sr-only">Send</span>
    </button>
  );

  return (
    <div className={`composer composer--${size}${leading ? " composer--leading" : ""}${mentions || projects ? " mention-composer" : ""}${correction ? " composer--fixed" : ""}`}
      data-rows={many ? "many" : "one"}>
      {correction ? <SpokenFixStrip correction={correction} onKeep={onKeep} /> : null}
      {leading ? <div className="composer__leading">{leading}</div> : null}
      <textarea
        ref={boxRef}
        className="composer__box"
        value={shown}
        data-live={live ? "true" : undefined}
        readOnly={Boolean(live)}
        onChange={(event) => onEdit(event.target.value, event.target.selectionStart)}
        onSelect={(event) => picker.onSelect(event.currentTarget.selectionStart)}
        onKeyDown={onKeyDown}
        onFocus={call ? reprobeVoiceInfo : undefined}
        aria-autocomplete={mentions || projects ? "list" : undefined}
        aria-controls={listOpen ? listId : undefined}
        aria-activedescendant={listOpen ? `${listId}-${picker.highlighted}` : undefined}
        placeholder={placeholder ?? "Message…"}
        disabled={disabled || sending}
        rows={size === "large" ? 3 : 1}
      />
      {listOpen ? <MentionList id={listId} options={picker.shown} active={picker.highlighted} onPick={picker.pick}
        trigger={picker.trigger} /> : null}
      {voice ? <MicButton onText={onSpoken} onError={voice.onError} disabled={disabled || sending} botId={voice.botId}
        correct={voice.correct} onLive={setLive} onChecked={onChecked} onCorrected={onCorrected} /> : null}
      {call && text.trim().length === 0 && !live && !allowEmpty && !disabled && !sending
        ? <CallButton name={call.name} onCall={call.onCall} />
        : sendButton}
    </div>
  );
}
