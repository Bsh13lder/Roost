// A task_cards line's body (roost/tasks/cards.py): server-made JSON, checked field by field; null for anything else.
export interface TaskCardsData {
  taskIds: string[];
  verb: "added" | "listed" | "tasks";
  more: number;
}

const VERBS: readonly string[] = ["added", "listed", "tasks"];

export function parseTaskCards(body: string): TaskCardsData | null {
  let value: unknown;
  try {
    value = JSON.parse(body);
  } catch {
    return null;
  }
  if (typeof value !== "object" || value === null) return null;
  const data = value as Record<string, unknown>;
  const ids = Array.isArray(data.task_ids) ? data.task_ids.filter((id): id is string => typeof id === "string") : [];
  if (ids.length === 0) return null;
  const verb = typeof data.verb === "string" && VERBS.includes(data.verb) ? (data.verb as TaskCardsData["verb"]) : "tasks";
  const more = typeof data.more === "number" && Number.isInteger(data.more) && data.more > 0 ? data.more : 0;
  return { taskIds: ids, verb, more };
}
