// The Ask card for a model change: the main bot proposes, nothing changes until Switch is clicked.
// Not now hides it in this browser only; once switched it folds to one line.
import { useState } from "react";
import { ErrorNotice } from "./ErrorNotice";
import { FoldCard, FoldedLine } from "./FoldCard";
import { describeError, setBotModel } from "../api/client";
import { effortLabel, type ModelSuggestionData } from "../lib/models";
import { announceTeamChanged } from "../lib/teamChanged";

const hiddenKey = (messageId: string) => `roost.modelCard.hidden.${messageId}`;

function wasHidden(messageId: string): boolean {
  try { return window.localStorage.getItem(hiddenKey(messageId)) === "1"; } catch { return false; }
}

function remember(messageId: string): void {
  try { window.localStorage.setItem(hiddenKey(messageId), "1"); } catch { /* the card just hides for now */ }
}

export interface ModelSuggestionCardProps {
  messageId: string;
  suggestion: ModelSuggestionData;
  tainted?: boolean; // the run that wrote it read outside content
}

export function ModelSuggestionCard({ messageId, suggestion, tainted = false }: ModelSuggestionCardProps) {
  const [switched, setSwitched] = useState(false);
  const [hidden, setHidden] = useState(() => wasHidden(messageId));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { bot, label, effort } = suggestion;
  const switchNow = async () => {
    setBusy(true);
    setError(null);
    try {
      await setBotModel(suggestion.bot_id, suggestion.model, effort);
      setSwitched(true);
      announceTeamChanged();
    } catch (err) {
      setError(describeError(err));
    } finally {
      setBusy(false);
    }
  };
  if (switched) {
    const how = effort ? ` at ${effortLabel(effort).toLowerCase()} effort` : "";
    return <FoldedLine ariaLabel={`Switched ${bot}`}>Switched {bot} to {label}{how}</FoldedLine>;
  }
  if (hidden) return null;
  return (
    <FoldCard ariaLabel={`Switch ${bot} to ${label}`} title={`Switch ${bot} to ${label}?`} explanation={suggestion.reason}
      footer={<>
        <button type="button" className="btn btn--quiet btn--small" onClick={() => { remember(messageId); setHidden(true); }}>Not now</button>
        <button type="button" className="btn btn--primary btn--small" onClick={() => void switchNow()} disabled={busy}>Switch</button>
      </>}>
      {tainted ? <p className="fold-card__taint" role="note">This run read outside content.</p> : null}
      {error ? <ErrorNotice message={error} /> : null}
    </FoldCard>
  );
}
