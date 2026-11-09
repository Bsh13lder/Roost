import { Field } from "../../ui/Field";
import { Input } from "../../ui/Input";
import { Switch } from "../../ui/Switch";
import type { WatchIn, WatchOut } from "../../api/routines";
import { WATCH_DEFAULT_MINUTES, WATCH_HINT, WATCH_LABEL, WATCH_MIN_MINUTES } from "./constants";

// The editor's watch as typed: the minutes stay text until Save, so a half-typed number never jumps.
export interface WatchDraft {
  on: boolean;
  url: string;
  part: string;
  every: string;
}

export const watchDraft = (watch: WatchOut | null | undefined): WatchDraft => ({
  on: Boolean(watch), url: watch?.url ?? "", part: watch?.part ?? "",
  every: String(watch?.every_min ?? WATCH_DEFAULT_MINUTES),
});

// What Save sends: null when the switch is off. The server checks the address and the minutes.
export function watchIn(draft: WatchDraft): WatchIn | null {
  if (!draft.on) return null;
  const minutes = Number.parseInt(draft.every, 10);
  return { url: draft.url.trim(), part: draft.part.trim(), every_min: Number.isNaN(minutes) ? WATCH_DEFAULT_MINUTES : minutes };
}

export interface WatchFieldsProps {
  value: WatchDraft;
  onChange: (draft: WatchDraft) => void;
}

// "Only run when the page changes": the switch, the page's address, the part in plain words and how often.
export function WatchFields({ value, onChange }: WatchFieldsProps) {
  const set = (changes: Partial<WatchDraft>) => onChange({ ...value, ...changes });
  return (
    <div className="routine-watch">
      <Switch checked={value.on} onChange={(on) => set({ on })}>{WATCH_LABEL}</Switch>
      {value.on ? (
        <>
          <p className="routine-watch__hint">{WATCH_HINT}</p>
          <Field label="Page address">
            <Input type="url" inputMode="url" placeholder="https://web.whatsapp.com" value={value.url}
              onChange={(event) => set({ url: event.target.value })} />
          </Field>
          <Field label="What part to watch" hint="In plain words, like “the physio chat” or “the price box”. Empty: the whole page." optional>
            <Input value={value.part} placeholder="the physio chat" onChange={(event) => set({ part: event.target.value })} />
          </Field>
          <Field label="Check every (minutes)" hint={`At least ${WATCH_MIN_MINUTES} minutes.`}>
            <Input type="number" inputMode="numeric" min={WATCH_MIN_MINUTES} value={value.every}
              onChange={(event) => set({ every: event.target.value })} />
          </Field>
        </>
      ) : null}
    </div>
  );
}
