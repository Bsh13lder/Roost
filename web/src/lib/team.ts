// web/src/lib/team.ts — the main bot first (D-B), reading a suggestion card's
// body (D-D) and a "Created <name>" card's body (S1.3).
import type { AvatarBadge, BotOut, BotRole, CreatedCardData, RobotScreen, SuggestionCardData } from "../api/types";
import { AVATAR_SHAPES as SHAPES, BOT_ROLES, ROBOT_SCREENS, robotScreen } from "../components/robot/look";

const BADGES: readonly AvatarBadge[] = ["none", "tasks", "finance", "notes", "docs", "inbox"];

// A card's screen style: one of the three, or none (a card from before the robots).
const screenOf = (value: unknown): RobotScreen | null =>
  value === undefined ? robotScreen(undefined) : (ROBOT_SCREENS as readonly unknown[]).includes(value) ? (value as RobotScreen) : null;
const HEX_COLOR = /^#[0-9a-fA-F]{6}$/;
// A card's role: kept when it is one this web knows; anything else is left out (it counts as general).
const roleOf = (value: unknown) => ((BOT_ROLES as readonly unknown[]).includes(value) ? { role: value as BotRole } : {});

export function orderTeam(bots: readonly BotOut[]): BotOut[] {
  // Boolean() first: a bot from older data may lack the flag, and
  // Number(undefined) is NaN, which sort treats as "keep in place".
  return [...bots].sort((a, b) => Number(Boolean(b.is_primary)) - Number(Boolean(a.is_primary)));
}

export function primaryBot(bots: readonly BotOut[]): BotOut | undefined {
  return bots.find((bot) => bot.is_primary);
}

// The card body comes from the server but was written by a model: check
// every field instead of trusting the shape. Any `roles` on an older card
// are ignored: every bot has every tool now (Ruling 28).
export function parseSuggestion(body: string): SuggestionCardData | null {
  try {
    const data = JSON.parse(body);
    const avatar = data?.avatar;
    const valid =
      typeof data?.name === "string" &&
      typeof data?.job === "string" &&
      SHAPES.includes(avatar?.shape) &&
      typeof avatar?.color === "string" &&
      HEX_COLOR.test(avatar.color) &&
      BADGES.includes(avatar?.badge);
    const screen = screenOf(avatar?.screen);
    if (!valid || screen === null) return null;
    return { name: data.name, job: data.job, avatar: { shape: avatar.shape, color: avatar.color, badge: avatar.badge, screen, ...roleOf(avatar.role) } };
  } catch {
    return null; // not JSON: no card, the row renders as plain text instead
  }
}

export function parseCreatedCard(body: string): CreatedCardData | null {
  try {
    const data = JSON.parse(body);
    const avatar = data?.avatar;
    const ok = typeof data?.bot_id === "string" && typeof data?.name === "string" && typeof data?.job === "string"
      && typeof data?.instructions === "string" && SHAPES.includes(avatar?.shape)
      && typeof avatar?.color === "string" && HEX_COLOR.test(avatar.color);
    const screen = screenOf(avatar?.screen);
    if (!ok || screen === null) return null;
    return { bot_id: data.bot_id, name: data.name, job: data.job, instructions: data.instructions,
             avatar: { shape: avatar.shape, color: avatar.color, badge: "none", screen, ...roleOf(avatar.role) },
             ...(data.checked === true ? { checked: true } : {}) };
  } catch {
    return null; // not JSON: no card, the row renders as plain text instead
  }
}

// A page's own copy (just saved) against the live store's (may be older): keep
// the newer edit, and always the live status and activity.
export function freshest(local: BotOut, live: BotOut | undefined): BotOut {
  if (!live) return local;
  const base = live.updated_at > local.updated_at ? live : local;
  return { ...base, status: live.status, activity: live.activity };
}
