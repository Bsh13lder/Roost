// web/src/lib/keyRequests.ts — the Add a key card's message (Connectors): its body is
// {"request_id", "service", "host"}; anything else is not a card. Kept out of the card's lazy chunk.
export function parseKeyRequestMessage(body: string): string | null {
  try {
    const data: unknown = JSON.parse(body);
    const id = (data as { request_id?: unknown } | null)?.request_id;
    return typeof id === "string" && id ? id : null;
  } catch {
    return null;
  }
}
