// web/src/lib/madeBy.ts: tasks a bot made (board toggles, 2026-10-26). `created_by_bot` names the bot; NULL is the
// user, or a bot since retired, which counts as the user's.
export const isBotMade = (row: { created_by_bot?: string | null }): boolean => Boolean(row.created_by_bot);

/** The rows with bot-made ones left out unless they are shown; the same array when nothing is cut. */
export function keepMade<T extends { created_by_bot?: string | null }>(rows: readonly T[], show: boolean): readonly T[] {
  return show ? rows : rows.filter((row) => !isBotMade(row));
}

/** How many bot-made rows `keepMade` leaves out. */
export const botMadeCount = (rows: readonly { created_by_bot?: string | null }[]): number => rows.filter(isBotMade).length;
