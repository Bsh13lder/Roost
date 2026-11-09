export type LiveMode = "view" | "control";

// The live screen's socket: the gateway's view-only RFB relay (WS /api/bots/{id}/live).
export function liveUrl(botId: string, mode: LiveMode = "view"): string {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${protocol}//${window.location.host}/api/bots/${encodeURIComponent(botId)}/live?mode=${mode}`;
}

export function openLiveSocket(botId: string, mode: LiveMode = "view"): WebSocket {
  return new WebSocket(liveUrl(botId, mode));
}
