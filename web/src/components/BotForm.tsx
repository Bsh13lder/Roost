import { useId, useState } from "react";
import { Avatar } from "./Avatar";
import { AvatarStudio } from "./avatar/AvatarStudio";
import { ErrorNotice } from "./ErrorNotice";
import { InstructionsCount } from "./InstructionsCount";
import { DEFAULT_LENSBOT_SHAPE } from "./robot/look";
import { nextBotColor } from "./robot/palette";
import type { AvatarOut } from "../api/types";
import { BOT_LIMITS } from "../lib/botProfile";
import { checkJob, checkName, instructionsOver } from "../lib/botFields";

export interface BotFormValues {
  name: string;
  job: string;
  instructions: string;
  avatar: AvatarOut;
  template_id: string | null;
}

export interface BotFormProps {
  initial?: BotFormValues;
  submitLabel: string;
  onSubmit: (values: BotFormValues) => void;
}

// A new bot's form: a dome ghost in the first colour no teammate wears (avatars v5).
export function newBotValues(usedColors: readonly string[]): BotFormValues {
  return {
    name: "", job: "", instructions: "", template_id: null,
    avatar: { shape: DEFAULT_LENSBOT_SHAPE, color: nextBotColor(usedColors), badge: "none" },
  };
}

// What stops a submit, checked the way the server checks it; null when it can go.
function problemWith(values: BotFormValues): string | null {
  if (instructionsOver(values.instructions) > 0) return "The instructions are too long — shorten them to create the bot.";
  return checkName(values.name) ?? checkJob(values.job);
}

function Preview({ values }: { values: BotFormValues }) {
  return (
    <aside className="bot-form__preview" aria-label="Preview">
      <div className="bot-form__stage">
        <Avatar avatar={values.avatar} status="resting" size={168} label={false} decorative />
      </div>
      <div className="bot-form__preview-text">
        <p className="bot-form__preview-name">{values.name.trim() || "Your new bot"}</p>
        <p className="bot-form__preview-job">{values.job.trim() || "Give it a job to do"}</p>
      </div>
    </aside>
  );
}

function InstructionsField({ value, onChange }: { value: string; onChange: (text: string) => void }) {
  const id = useId();
  return (
    <div className="field">
      <span className="field__label">
        <label htmlFor={id}>Instructions</label> <span className="field__optional">optional</span>
      </span>
      <textarea id={id} className="input input--area" value={value} rows={4} onChange={(event) => onChange(event.target.value)}
        placeholder="How it should work, what to avoid, when to ask you first." />
      <p className="field__hint">Saved in five parts: Who you are and context · What you do · Rules · Tone · Team. Plain text is sorted into them.</p>
      <InstructionsCount text={value} />
    </div>
  );
}

// New bot: name, job, instructions and a look (S1.7), with a live preview of its ghost.
// No roles and no badges: every bot has every tool.
export function BotForm({ initial, submitLabel, onSubmit }: BotFormProps) {
  const [values, setValues] = useState<BotFormValues>(() => initial ?? newBotValues([]));
  const [problem, setProblem] = useState<string | null>(null);
  const set = (patch: Partial<BotFormValues>) => setValues((prev) => ({ ...prev, ...patch }));
  const submit = () => {
    const found = problemWith(values);
    setProblem(found);
    if (!found) onSubmit({ ...values, name: values.name.trim(), job: values.job.trim() });
  };
  return (
    <form className="bot-form" onSubmit={(event) => { event.preventDefault(); submit(); }}>
      <Preview values={values} />
      <div className="bot-form__fields">
        <label className="field">
          <span className="field__label">Name</span>
          <input className="input" value={values.name} onChange={(event) => set({ name: event.target.value })}
            maxLength={BOT_LIMITS.name} placeholder="Scout" required />
        </label>
        <label className="field">
          <span className="field__label">Job</span>
          <input className="input" value={values.job} onChange={(event) => set({ job: event.target.value })}
            maxLength={BOT_LIMITS.job} placeholder="Finds things on the web for me" required />
        </label>
        <InstructionsField value={values.instructions} onChange={(instructions) => set({ instructions })} />
        <AvatarStudio value={values.avatar} preview={false} onChange={(avatar) => set({ avatar })} />
        {problem ? <ErrorNotice message={problem} /> : null}
        <div className="bot-form__actions">
          <button type="submit" className="btn btn--primary">{submitLabel}</button>
        </div>
      </div>
    </form>
  );
}
