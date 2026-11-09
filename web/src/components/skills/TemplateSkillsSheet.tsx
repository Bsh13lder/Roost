import { useState } from "react";
import { Button } from "../../ui/Button";
import { Sheet } from "../../ui/Sheet";
import { describeError } from "../../api/client";
import * as skillsApi from "../../api/skills";
import type { TemplateSkillCheck } from "../../api/types";
import { ADD_SKILLS, ADD_TITLE, HAVE_IT, SKIP } from "./constants";

export interface TemplateSkillsSheetProps {
  botId: string;
  skills: readonly TemplateSkillCheck[];
  onDone: () => void; // after Add skills or Skip: on to the new bot
}

// After Create from a file (Skills design §5): its skills, each ticked unless you already have that name, readable
// in full. Only Add skills adds the ticked ones, marked as from outside content; Skip adds nothing.
export default function TemplateSkillsSheet({ botId, skills, onDone }: TemplateSkillsSheetProps) {
  const [ticked, setTicked] = useState<ReadonlySet<number>>(
    () => new Set(skills.flatMap((skill, index) => (skill.have ? [] : [index]))));
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const toggle = (index: number) => setTicked((now) => {
    const next = new Set(now);
    if (next.has(index)) next.delete(index); else next.add(index);
    return next;
  });
  const add = async () => {
    const chosen = skills.filter((_, index) => ticked.has(index))
      .map((skill) => ({ name: skill.name, use_when: skill.use_when, steps: skill.body }));
    if (chosen.length === 0) { onDone(); return; }
    setBusy(true);
    setError(null);
    try { await skillsApi.importSkills(chosen, botId); onDone(); } catch (err) { setError(describeError(err)); } finally { setBusy(false); }
  };
  return (
    <Sheet open title={ADD_TITLE} onOpenChange={(open) => { if (!open) onDone(); }}
      footer={(
        <>
          <Button variant="ghost" disabled={busy} onClick={onDone}>{SKIP}</Button>
          <Button variant="primary" loading={busy} onClick={() => void add()}>{ADD_SKILLS}</Button>
        </>
      )}>
      <ul className="template-skills__list">
        {skills.map((skill, index) => (
          <li key={`${skill.name}-${index}`} className="template-skill">
            <label className="template-skill__head">
              <input type="checkbox" checked={ticked.has(index)} disabled={skill.have} onChange={() => toggle(index)} />
              <span className="template-skill__text">
                <span className="template-skill__name">{skill.name}</span>
                <span className="template-skill__when">{skill.use_when}</span>
                {skill.have ? <span className="template-skill__have">{HAVE_IT}</span> : null}
              </span>
            </label>
            <details><summary>Steps</summary><pre className="template-skill__steps">{skill.body}</pre></details>
          </li>
        ))}
      </ul>
      {error ? <p className="skill-editor__error" role="alert">{error}</p> : null}
    </Sheet>
  );
}
