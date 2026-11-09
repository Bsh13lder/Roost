import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ErrorNotice } from "../components/ErrorNotice";
import { BackIcon } from "../components/icons";
import { InstructionsCount } from "../components/InstructionsCount";
import * as botsApi from "../api/bots";
import { describeError } from "../api/client";
import { instructionsOver } from "../lib/botFields";

function useSavedInstructions(botId: string | undefined) {
  const [saved, setSaved] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    if (!botId) return;
    let live = true;
    botsApi.getBot(botId)
      .then((bot) => { if (live) { setSaved(bot.instructions); setDraft(bot.instructions); } })
      .catch((err: unknown) => { if (live) setError(describeError(err)); });
    return () => { live = false; };
  }, [botId]);
  return { saved, draft, setDraft, error, setError };
}

// Full-screen editor (S1.6). Save stays off until the text changes, and an
// over-limit draft stays here: it is never sent.
export function Instructions() {
  const { botId } = useParams<{ botId: string }>();
  const navigate = useNavigate();
  const { saved, draft, setDraft, error, setError } = useSavedInstructions(botId);
  const [saving, setSaving] = useState(false);
  if (!botId) return null;
  const canSave = saved !== null && draft !== saved && instructionsOver(draft) === 0 && !saving;
  const save = async () => {
    if (!canSave) return;
    setSaving(true);
    setError(null);
    try {
      await botsApi.updateBot(botId, { instructions: draft });
      navigate(`/bots/${botId}?panel=settings`);
    } catch (err) {
      setError(describeError(err));
      setSaving(false);
    }
  };
  return (
    <div className="instructions-page">
      <header className="instructions-page__head">
        <Link to={`/bots/${botId}?panel=settings`} className="icon-btn" aria-label="Back"><BackIcon /></Link>
        <h1 className="instructions-page__title">Instructions</h1>
        <button type="button" className="btn btn--primary btn--small instructions-page__save" onClick={() => void save()} disabled={!canSave}>Save</button>
      </header>
      {error ? <ErrorNotice message={error} /> : null}
      {saved === null ? (error ? null : <p className="page-loading">Loading&hellip;</p>) : (
        <>
          <textarea aria-label="Instructions" className="instructions-page__text" value={draft}
            placeholder="How it should work, what to avoid, when to ask you first." onChange={(e) => setDraft(e.target.value)} />
          <InstructionsCount text={draft} />
        </>
      )}
    </div>
  );
}
