import { useState } from "react";
import { Link } from "react-router-dom";
import { Avatar } from "./Avatar";
import { ErrorNotice } from "./ErrorNotice";
import { FoldCard, FoldedLine } from "./FoldCard";
import * as botsApi from "../api/bots";
import { describeError } from "../api/client";
import type { BotOut, CreatedCardData } from "../api/types";
import { announceTeamChanged } from "../lib/teamChanged";

// The created card's mark when the chat had read web content (owner, 2026-10-29).
export const CREATED_CHECKED_TEXT =
  "Auto-checked: this chat had read web content, so Fable checked this bot matches what you asked.";

// "Created <name>" (S1.3, Ruling 29): what the main bot just made, in full.
// Undo retires the new bot with the normal confirm.
export function CreatedBotCard({ card, team }: { card: CreatedCardData; team: readonly BotOut[] }) {
  const [state, setState] = useState<"open" | "undoing" | "undone">("open");
  const [error, setError] = useState<string | null>(null);
  if (state === "undone") return <FoldedLine ariaLabel={`Undone: ${card.name}`}>Undone: {card.name} was retired.</FoldedLine>;
  if (team.length > 0 && !team.some((bot) => bot.id === card.bot_id)) {
    return <FoldedLine ariaLabel={`${card.name} was retired`}>{card.name} was retired.</FoldedLine>;
  }
  const undo = async () => {
    if (!window.confirm(`Retire ${card.name}? This deletes the bot that was just created, with its chats.`)) return;
    setState("undoing");
    setError(null);
    try {
      await botsApi.deleteBot(card.bot_id);
      announceTeamChanged();
      setState("undone");
    } catch (err) {
      setError(describeError(err));
      setState("open");
    }
  };
  return (
    <FoldCard ariaLabel={`Created ${card.name}`} title={`Created ${card.name}`} explanation={card.job}
      icon={<Avatar avatar={card.avatar} status="resting" size={32} label={false} decorative />}
      footer={<>
        <Link className="btn btn--quiet btn--small" to={`/bots/${card.bot_id}`}>Open</Link>
        <button type="button" className="btn btn--quiet btn--small" onClick={() => void undo()} disabled={state === "undoing"}>Undo</button>
      </>}>
      {card.checked ? <p className="fold-card__taint" role="note">{CREATED_CHECKED_TEXT}</p> : null}
      <details className="fold-card__details" open>
        <summary>Instructions</summary>
        <p className="fold-card__instructions">{card.instructions || "No instructions."}</p>
      </details>
      {error ? <ErrorNotice message={error} /> : null}
    </FoldCard>
  );
}
