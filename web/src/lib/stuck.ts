// web/src/lib/stuck.ts — reading a Stuck card's chat message (stuck flow, Piece A), and your
// cards as this page knows them: loaded once (GET /api/stuck), then kept current by stuck_card frames.
import type { BotStatus, StuckCardOut, StuckMessageData, StuckReason } from "../api/types";
import { linkHost } from "./linkHost";

const REASONS: readonly StuckReason[] = ["challenge", "login", "code", "refused", "asked"];

const isText = (value: unknown): value is string => typeof value === "string";
const isFilled = (value: unknown): value is string => isText(value) && value !== "";

// The body is the server's JSON, but its note was written by a model: check every field. A body
// that fails renders as plain text instead. Only an http(s) address is kept: any other (about:blank,
// when the bot asked for help before opening a page) means the card has no address. The card keeps
// its buttons, because a card that can't be cleared from the chat would leave the bot Stuck.
const SECRET_KINDS: readonly unknown[] = ["password", "code"];

export function parseStuckMessage(body: string): StuckMessageData | null {
  try {
    const data = JSON.parse(body);
    const ok = isFilled(data?.card_id) && isFilled(data?.bot_id) && REASONS.includes(data?.reason)
      && isText(data?.host) && isText(data?.url) && isText(data?.note)
      && typeof data?.suggest_main_browser === "boolean" && isText(data?.line);
    if (!ok) return null;
    const web = linkHost(data.url) !== null;
    return {
      card_id: data.card_id, bot_id: data.bot_id, reason: data.reason,
      host: web ? data.host : "", url: web ? data.url : "",
      note: data.note, suggest_main_browser: data.suggest_main_browser, line: data.line,
      ...(data.sign_in === true && web ? { sign_in: true } : {}), // an older body has none: a plain Stuck card
      ...(data.sign_in === true && web && SECRET_KINDS.includes(data.secret_field) ? { secret_field: data.secret_field } : {}),
    };
  } catch {
    return null; // not JSON: no card, the row renders as plain text instead
  }
}

// The card's title, in the chat and in Home's My turn: the site it is stuck on, or
// "Needs your help" when it has no web address.
export function stuckTitle(host: string, url: string, signIn = false): string {
  if (!host || linkHost(url) === null) return "Needs your help";
  return signIn ? `Sign in on ${host}` : `Stuck on ${host}`;
}

// A bot on a Sign-in card is waiting for you, not Stuck: the server's status line starts with this lead
// (roost/signin/texts.py SIGN_IN_WAIT_LEAD), and only a sign-in card's line can (a Stuck line starts "Stuck"
// or "Needs your help"). The host is what follows " to ", or "" when the card has none.
export const SIGN_IN_WAIT = "Waiting for you to sign in";
// Every sign-in surface says it (roost/signin/texts.py NEVER_SEES_PASSWORD).
export const NEVER_SEES_PASSWORD = "Roost never sees your password.";

export function signInWaitHost(status: BotStatus, activity: string | null | undefined): string | null {
  if (status !== "stuck" || !activity?.startsWith(SIGN_IN_WAIT)) return null;
  return activity.slice(SIGN_IN_WAIT.length).replace(/^ to /, "").replace(/\.$/, "").trim();
}

// A card's row in Home's My turn: a Sign-in card asks you to sign in, any other says where it is stuck.
export function myTurnLine(botName: string, card: StuckCardOut): string {
  if (card.sign_in && card.host) return `${botName} needs you to sign in to ${card.host}`;
  return `${botName} · ${stuckTitle(card.host, card.url)}`;
}

// The loaded open cards with every live stuck_card frame on top: the live copy is the newer one.
export function mergeStuck(
  rest: readonly StuckCardOut[],
  live: Readonly<Record<string, StuckCardOut>>,
): Record<string, StuckCardOut> {
  return { ...Object.fromEntries(rest.map((card) => [card.id, card])), ...live };
}

// The cards still waiting on you, newest first (Home's My turn).
export function openStuckCards(cards: Readonly<Record<string, StuckCardOut>>): StuckCardOut[] {
  return Object.values(cards)
    .filter((card) => card.state === "open")
    .sort((a, b) => b.created_at.localeCompare(a.created_at));
}
