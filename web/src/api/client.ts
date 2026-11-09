import type { BotOut } from "./types";

// Thin fetch wrapper shared by every api/*.ts module. Same-origin
// relative paths only (the dev server proxies /api, production serves
// the SPA and the API from the same gateway process — see
// roost/gateway/routes/static.py) — never a hardcoded host:port here.

export class ApiError extends Error {
  readonly status: number;
  // The parsed JSON error body, when there was one (a 409 carries the stored
  // copy in it, M2 D4); undefined for a non-JSON body.
  readonly body: unknown;

  constructor(status: number, message: string, body: unknown = undefined) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.body = body;
  }
}

async function parseError(response: Response): Promise<{ message: string; body: unknown }> {
  const fallback = `Request failed (${response.status})`;
  try {
    const body: unknown = await response.json();
    const detail = (body as { detail?: unknown } | null)?.detail;
    return { message: typeof detail === "string" ? detail : fallback, body };
  } catch {
    // Non-JSON error body — the generic message, no body.
    return { message: fallback, body: undefined };
  }
}

// A failed response as an ApiError carrying the server's plain `detail`.
export async function errorFrom(response: Response): Promise<ApiError> {
  const { message, body } = await parseError(response);
  return new ApiError(response.status, message, body);
}

async function readResponse<T>(response: Response): Promise<T> {
  if (!response.ok) throw await errorFrom(response);
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

// Shared "turn a caught error into a user-facing sentence" helper —
// every page-mount fetch (Layout, Talk, Desk, NewBot) uses this instead
// of letting a rejection surface only as a console warning (project
// rule: never silently swallow errors).
export function describeError(err: unknown): string {
  return err instanceof ApiError ? err.message : "Something went wrong. Please try again.";
}

export async function apiRequest<T>(
  method: string,
  path: string,
  body?: unknown,
): Promise<T> {
  const response = await fetch(path, {
    method,
    credentials: "include",
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  return readResponse<T>(response);
}

// A save sent as the page goes away (pagehide, lead 01b): keepalive lets the request outlive the page, so nobody
// waits for the answer. A failure can only be noted in the console; the page is already gone.
export function apiSendOnLeave(method: string, path: string, body: unknown): void {
  fetch(path, {
    method, credentials: "include", keepalive: true,
    headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  }).catch((err: unknown) => console.warn("A save sent while leaving the page failed:", err));
}

// A raw upload (a PDF file, M2): the body goes as-is with its own content type. A call hands over a signal so a
// hearing that takes too long can be cut short.
export async function apiUpload<T>(path: string, file: Blob, contentType: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(path, {
    method: "POST", credentials: "include", headers: { "Content-Type": contentType }, body: file, signal,
  });
  return readResponse<T>(response);
}

// Choose a bot's model and effort; null for either means the default (PUT /api/bots/{id}/model).
export function setBotModel(botId: string, model: string | null, effort: BotOut["effort"]): Promise<BotOut> {
  return apiRequest<BotOut>("PUT", `/api/bots/${botId}/model`, { model, effort });
}
