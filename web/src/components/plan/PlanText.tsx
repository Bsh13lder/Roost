import { useEffect, useState } from "react";
import { Button } from "../../ui/Button";
import { Textarea } from "../../ui/Textarea";
import { describeError } from "../../api/client";
import * as planApi from "../../api/plan";
import type { PlanOut } from "../../api/plan";
import { CONFLICT_TEXT } from "./constants";
import { currentFromConflict } from "./planConflict";

export interface PlanTextProps {
  botId: string;
  plan: PlanOut;
  onSaved: (plan: PlanOut) => void;
}

// Edit as text: the Plan file itself. Save sends the revision it read. If the Plan moved on meanwhile, the newer
// copy is shown beside your text with Use theirs or Keep mine; nothing is overwritten without that choice.
export function PlanText({ botId, plan, onSaved }: PlanTextProps) {
  const [base, setBase] = useState({ content: plan.content, revision: plan.revision });
  const [draft, setDraft] = useState(plan.content);
  const [newer, setNewer] = useState<PlanOut | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [saving, setSaving] = useState(false);

  // A newer Plan (a bot wrote) replaces the text only while you have typed nothing of your own.
  useEffect(() => {
    if (plan.revision > base.revision && draft === base.content) {
      setBase({ content: plan.content, revision: plan.revision });
      setDraft(plan.content);
    }
  }, [plan, base, draft]);

  const save = async (revision: number) => {
    setSaving(true);
    setError(null);
    setSaved(false);
    try {
      const next = await planApi.putPlan(botId, draft, revision);
      setBase({ content: next.content, revision: next.revision });
      setDraft(next.content);
      setNewer(null);
      setSaved(true);
      onSaved(next);
    } catch (err) {
      const current = currentFromConflict(err);
      if (current) setNewer(current); else setError(describeError(err));
    } finally {
      setSaving(false);
    }
  };
  const useTheirs = () => {
    if (!newer) return;
    setBase({ content: newer.content, revision: newer.revision });
    setDraft(newer.content);
    setNewer(null);
    onSaved(newer);
  };

  return (
    <div className="plan-text">
      <Textarea aria-label="Plan text" value={draft} spellCheck={false} onChange={(event) => { setDraft(event.target.value); setSaved(false); }} />
      {newer ? (
        <div className="plan-text__conflict" role="status">
          <p>{CONFLICT_TEXT}</p>
          <Textarea aria-label="Newer copy" readOnly value={newer.content} />
          <div className="plan-text__buttons">
            <Button size="sm" variant="secondary" onClick={useTheirs}>Use theirs</Button>
            <Button size="sm" variant="primary" loading={saving} onClick={() => void save(newer.revision)}>Keep mine</Button>
          </div>
        </div>
      ) : null}
      {error ? <p className="plan-text__error" role="alert">{error}</p> : null}
      <div className="plan-text__buttons">
        <Button variant="primary" size="sm" loading={saving} disabled={draft === base.content} onClick={() => void save(base.revision)}>Save</Button>
        {saved ? <span className="plan-text__saved" role="status">Saved</span> : null}
      </div>
    </div>
  );
}
