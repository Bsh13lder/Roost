import { useCallback } from "react";
import { useNavigate } from "react-router-dom";
import * as botsApi from "../api/bots";
import type { BotOut } from "../api/types";
import { announceTeamChanged } from "../lib/teamChanged";

export const RETIRE_LABEL = "Retire this bot";
export const RETIRE_MAIN_HINT = "Make another bot the main bot first.";
export const retireQuestion = (name: string) =>
  `Retire ${name}? This closes its computer and deletes it with all its chats. This can't be undone.`;

// Retire this bot, after the browser's own confirm: the bot goes, the team list hears it, and Home opens.
// Answers false when the confirm was declined. A failure is the caller's to say (it rejects).
export function useRetireBot(bot: Pick<BotOut, "id" | "name">): () => Promise<boolean> {
  const navigate = useNavigate();
  return useCallback(async () => {
    if (!window.confirm(retireQuestion(bot.name))) return false;
    await botsApi.deleteBot(bot.id);
    announceTeamChanged();
    navigate("/", { replace: true });
    return true;
  }, [bot.id, bot.name, navigate]);
}
