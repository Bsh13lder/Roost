// The words on the profile's rows (restructure slice 3).
import type { BotStatus, DeskStatusOut } from "../api/types";

export type ComputerWord = "Idle" | "On it" | "Asleep";

// "Asleep" when the computer is not running, "On it" while the bot works, "Idle" otherwise. With no reading of the
// computer yet, the bot's status alone answers.
export function computerWord(status: BotStatus, desk: DeskStatusOut | null): ComputerWord {
  if (desk && desk.browser !== "running") return "Asleep";
  return status === "on_it" ? "On it" : "Idle";
}

export const routinesOnLabel = (on: number): string => `${on} on`;
