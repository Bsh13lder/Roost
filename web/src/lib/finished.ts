// web/src/lib/finished.ts: which tasks are finished (Show finished, lead task 14). Finished is closed: done, failed
// or cancelled, the same set the project page's Done group and the calendar's quiet chips use.
const FINISHED: ReadonlySet<string> = new Set(["done", "failed", "cancelled"]);

export const isFinished = (task: { status?: string }): boolean => task.status !== undefined && FINISHED.has(task.status);

/** The rows with finished ones left out unless they are shown; the same array when nothing is cut. */
export function keepShown<T extends { status?: string }>(rows: readonly T[], show: boolean): readonly T[] {
  return show ? rows : rows.filter((row) => !isFinished(row));
}

/** How many finished rows `keepShown` leaves out. */
export const finishedCount = (rows: readonly { status?: string }[]): number => rows.filter(isFinished).length;
