// SuggestionCard.tsx — D-D: a proposed teammate, on the FoldCard shell. Nothing
// is created until "Create this bot" is clicked, which calls the normal
// create-bot API; then (or when a bot of that name exists) it folds to one line.
import { useState } from "react";
import { Link } from "react-router-dom";
import { Avatar } from "./Avatar";
import { ErrorNotice } from "./ErrorNotice";
import { FoldCard, FoldedLine } from "./FoldCard";
import * as botsApi from "../api/bots";
import { describeError } from "../api/client";
import type { BotOut, SuggestionCardData } from "../api/types";
import { announceTeamChanged } from "../lib/teamChanged";

export interface SuggestionCardProps {
  suggestion: SuggestionCardData;
  team: readonly BotOut[];
  // The run that wrote it read outside content (spec §8.2): its job text
  // may be injected, and one click makes it lasting prompt text.
  tainted?: boolean;
}

function CardNotes({ tainted, error }: { tainted: boolean; error: string | null }) {
  return (
    <>
      {tainted ? <p className="fold-card__taint" role="note">This run read outside content.</p> : null}
      {error ? <ErrorNotice message={error} /> : null}
    </>
  );
}

export function SuggestionCard({ suggestion, team, tainted = false }: SuggestionCardProps) {
  const [createdId, setCreatedId] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const existing = team.find((bot) => bot.name.toLowerCase() === suggestion.name.toLowerCase());
  const openId = createdId ?? existing?.id;

  const create = async () => {
    setCreating(true);
    setError(null);
    try {
      const avatar = { ...suggestion.avatar, badge: "none" as const };
      const bot = await botsApi.createBot({ name: suggestion.name, job: suggestion.job, instructions: "", avatar });
      setCreatedId(bot.id);
      announceTeamChanged();
    } catch (err) {
      setError(describeError(err));
    } finally {
      setCreating(false);
    }
  };

  if (openId) {
    const open = <Link to={`/bots/${openId}`} className="btn btn--quiet btn--small">Open</Link>;
    return <FoldedLine ariaLabel={`Created ${suggestion.name}`} action={open}>Created {suggestion.name}</FoldedLine>;
  }
  return (
    <FoldCard ariaLabel={`Suggested bot: ${suggestion.name}`} title={`Suggested bot: ${suggestion.name}`} explanation={suggestion.job}
      icon={<Avatar avatar={suggestion.avatar} status="resting" size={32} label={false} decorative />}
      footer={<>
        <span className="fold-card__note">Nothing is created until you click.</span>
        <button type="button" className="btn btn--primary btn--small" onClick={() => void create()} disabled={creating}>
          Create this bot
        </button>
      </>}>
      {tainted || error ? <CardNotes tainted={tainted} error={error} /> : null}
    </FoldCard>
  );
}
