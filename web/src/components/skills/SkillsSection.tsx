import { useCallback, useEffect, useRef, useState } from "react";
import { Button } from "../../ui/Button";
import { describeError } from "../../api/client";
import * as skillsApi from "../../api/skills";
import type { SkillOut } from "../../api/skills";
import { useLiveState } from "../../hooks/useLiveStore";
import { ErrorNotice } from "../ErrorNotice";
import { NEW_SKILL, SKILLS_EMPTY } from "./constants";
import { SkillEditor } from "./SkillEditor";
import { SkillRow } from "./SkillRow";

type Editing = { skill: SkillOut | null } | null;

const replaceOrAdd = (list: readonly SkillOut[], next: SkillOut) =>
  list.some((one) => one.id === next.id) ? list.map((one) => (one.id === next.id ? { ...one, ...next } : one)) : [...list, next];

// The Skills fold on the Info tab: every skill with a switch for this bot, New skill, and the editor.
// It reloads on skills_changed. This file is the lazy chunk's entry, so none of it is in the main bundle.
export default function SkillsSection({ botId }: { botId: string }) {
  const version = useLiveState().skillVersion?.skills;
  const [skills, setSkills] = useState<readonly SkillOut[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [editing, setEditing] = useState<Editing>(null);
  const latest = useRef(0); // a slower, older load never wins
  const load = useCallback(() => {
    const ticket = ++latest.current;
    skillsApi.listSkills(botId)
      .then((loaded) => { if (ticket === latest.current) { setSkills(loaded); setError(null); } })
      .catch((err: unknown) => { if (ticket === latest.current) setError(describeError(err)); });
  }, [botId]);
  useEffect(() => load(), [load, version]);

  const toggle = async (skill: SkillOut, on: boolean) => {
    setBusy(skill.id);
    setError(null);
    try {
      const answer = await skillsApi.setSkillOn(botId, skill.id, on);
      setSkills((now) => (now ?? []).map((one) => (one.id === skill.id ? { ...one, on: answer.on } : one)));
    } catch (err) {
      setError(describeError(err));
    } finally {
      setBusy(null);
    }
  };
  return (
    <div className="skills">
      <div className="skills__head">
        <Button size="sm" variant="secondary" onClick={() => setEditing({ skill: null })}>{NEW_SKILL}</Button>
      </div>
      {skills?.length === 0 ? <p className="skills__empty">{SKILLS_EMPTY}</p> : null}
      <ul className="skills__list">
        {(skills ?? []).map((skill) => (
          <SkillRow key={skill.id} skill={skill} busy={busy === skill.id} onToggle={(one, on) => void toggle(one, on)}
            onOpen={(one) => setEditing({ skill: one })} />
        ))}
      </ul>
      {error ? <ErrorNotice message={error} onRetry={load} /> : null}
      {editing ? (
        <SkillEditor skill={editing.skill} onClose={() => setEditing(null)}
          onSaved={(saved) => { setSkills((now) => replaceOrAdd(now ?? [], saved)); setEditing(null); }}
          onDeleted={(id) => { setSkills((now) => (now ?? []).filter((one) => one.id !== id)); setEditing(null); }} />
      ) : null}
    </div>
  );
}
