import { useState } from "react";
import { Button } from "../../ui/Button";
import { Field } from "../../ui/Field";
import { Input } from "../../ui/Input";
import { Segmented } from "../../ui/Segmented";
import { Sheet } from "../../ui/Sheet";
import { Textarea } from "../../ui/Textarea";
import { describeError } from "../../api/client";
import { RevisionConflictError } from "../../api/conflict";
import * as skillsApi from "../../api/skills";
import type { SkillFields, SkillOut } from "../../api/skills";
import { RichText } from "../chat/RichText";
import {
  CONFLICT_TEXT, DELETE_QUESTION, FIELD_LABELS, KEEP_MINE, LOAD_LATEST, NEW_SKILL, SAVE_SKILL, SKILL_BODY_MAX,
  SKILL_NAME_MAX, SKILL_USE_WHEN_MAX,
} from "./constants";

export interface SkillEditorProps {
  skill: SkillOut | null; // null: a new one
  onClose: () => void;
  onSaved: (skill: SkillOut) => void;
  onDeleted: (id: string) => void;
}

type View = "write" | "preview";
type FieldErrors = Partial<Record<keyof SkillFields | "form", string>>;

const VIEWS = [{ id: "write", label: "Write" }, { id: "preview", label: "Preview" }] as const;

// The server's sentence goes under the field it is about ("The name must…", "Use when must…", "The steps…").
export function fieldOf(message: string): keyof FieldErrors {
  if (message.startsWith("The name") || message.startsWith("There is already a skill")) return "name";
  if (message.startsWith("Use when")) return "use_when";
  if (message.startsWith("The steps") || message.includes("in the steps")) return "body";
  return "form";
}

const fieldsOf = (skill: SkillOut | null): SkillFields =>
  ({ name: skill?.name ?? "", use_when: skill?.use_when ?? "", body: skill?.body ?? "" });

// A skill's form in a Sheet: Name, Use when and Steps (Write · Preview). Save skill is a revision check: when the
// skill changed meanwhile it offers Load the latest or Keep mine. Delete asks first.
export function SkillEditor({ skill, onClose, onSaved, onDeleted }: SkillEditorProps) {
  const [fields, setFields] = useState<SkillFields>(() => fieldsOf(skill));
  const [revision, setRevision] = useState(skill?.revision ?? 0);
  const [newer, setNewer] = useState<SkillOut | null>(null);
  const [errors, setErrors] = useState<FieldErrors>({});
  const [view, setView] = useState<View>("write");
  const [saving, setSaving] = useState(false);
  const [asking, setAsking] = useState(false);
  const set = (key: keyof SkillFields) => (value: string) => setFields((now) => ({ ...now, [key]: value }));

  const run = async (work: () => Promise<void>) => {
    setSaving(true);
    setErrors({});
    try { await work(); } catch (err) {
      if (err instanceof RevisionConflictError) { setNewer(err.current as SkillOut); return; }
      const message = describeError(err);
      setErrors({ [fieldOf(message)]: message });
    } finally { setSaving(false); }
  };
  const save = (base = revision) => run(async () => {
    onSaved(skill === null ? await skillsApi.addSkill(fields) : await skillsApi.saveSkill(skill.id, fields, base));
  });
  const keepMine = () => { const base = newer?.revision ?? revision; setNewer(null); setRevision(base); void save(base); };
  const loadLatest = () => { if (newer) { setFields(fieldsOf(newer)); setRevision(newer.revision); setNewer(null); } };
  const remove = () => run(async () => { if (skill) { await skillsApi.deleteSkill(skill.id); onDeleted(skill.id); } });

  return (
    <Sheet open title={skill ? skill.name : NEW_SKILL} onOpenChange={(open) => { if (!open) onClose(); }}
      footer={(
        <>
          {skill && !asking ? <Button variant="ghost" onClick={() => setAsking(true)}>Delete</Button> : null}
          <Button variant="ghost" onClick={onClose}>Close</Button>
          <Button variant="primary" loading={saving} onClick={() => void save()}>{SAVE_SKILL}</Button>
        </>
      )}>
      <div className="skill-editor">
        {newer ? (
          <div className="skill-editor__conflict" role="status">
            <p>{CONFLICT_TEXT}</p>
            <Button size="sm" variant="ghost" onClick={loadLatest}>{LOAD_LATEST}</Button>
            <Button size="sm" variant="primary" onClick={keepMine}>{KEEP_MINE}</Button>
          </div>
        ) : null}
        {asking ? (
          <div className="skill-editor__ask" role="group" aria-label="Are you sure?">
            <p>{DELETE_QUESTION}</p>
            <Button size="sm" variant="danger" loading={saving} onClick={() => void remove()}>Yes, delete it</Button>
            <Button size="sm" variant="ghost" onClick={() => setAsking(false)}>Cancel</Button>
          </div>
        ) : null}
        <Field label={FIELD_LABELS.name} error={errors.name ?? null}>
          <Input value={fields.name} maxLength={SKILL_NAME_MAX} onChange={(event) => set("name")(event.target.value)} />
        </Field>
        <Field label={FIELD_LABELS.use_when} error={errors.use_when ?? null}>
          <Input value={fields.use_when} maxLength={SKILL_USE_WHEN_MAX}
            onChange={(event) => set("use_when")(event.target.value)} />
        </Field>
        <Segmented label="Steps view" options={VIEWS} value={view} onChange={setView} />
        {view === "write" ? (
          <Field label={FIELD_LABELS.body} error={errors.body ?? null}>
            <Textarea value={fields.body} maxLength={SKILL_BODY_MAX} autoGrow
              onChange={(event) => set("body")(event.target.value)} />
          </Field>
        ) : (
          <div className="skill-editor__preview"><RichText text={fields.body} id="skill-preview" /></div>
        )}
        {errors.form ? <p className="skill-editor__error" role="alert">{errors.form}</p> : null}
      </div>
    </Sheet>
  );
}
