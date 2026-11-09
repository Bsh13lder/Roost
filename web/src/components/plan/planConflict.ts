import type { PlanOut } from "../../api/plan";

// The newer copy a 409 carries ({detail, current}), or null for any other error.
export function currentFromConflict(err: unknown): PlanOut | null {
  const body = (err as { status?: number; body?: unknown } | null);
  if (body?.status !== 409 || typeof body.body !== "object" || body.body === null) return null;
  const current = (body.body as { current?: unknown }).current;
  return typeof current === "object" && current !== null ? (current as PlanOut) : null;
}
