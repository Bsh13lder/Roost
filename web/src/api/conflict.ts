import { ApiError } from "./client";

// A save that carried a stale revision (M2 D4): the gateway answers 409 with
// the stored copy, so the editor can offer "Load the latest" or "Keep mine".
export class RevisionConflictError<T> extends Error {
  readonly current: T;

  constructor(current: T) {
    super("This changed somewhere else since you opened it.");
    this.name = "RevisionConflictError";
    this.current = current;
  }
}

function conflictBody(err: unknown): { current: unknown } | null {
  if (!(err instanceof ApiError) || err.status !== 409) return null;
  const body = err.body;
  return typeof body === "object" && body !== null && "current" in body ? (body as { current: unknown }) : null;
}

export async function withConflict<T, C>(request: Promise<T>): Promise<T> {
  try {
    return await request;
  } catch (err) {
    const conflict = conflictBody(err);
    if (conflict) throw new RevisionConflictError<C>(conflict.current as C);
    throw err;
  }
}
