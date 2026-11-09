// Nothing publishes a live frame for a newly created bot (no `bot_created`
// frame). A page that adds a bot in place (the Created card's Undo, a
// suggestion card in a chat) announces it, and Home reloads its chat list.
const TEAM_CHANGED = "roost:team-changed";

export function announceTeamChanged(): void {
  window.dispatchEvent(new Event(TEAM_CHANGED));
}

export function onTeamChanged(listener: () => void): () => void {
  window.addEventListener(TEAM_CHANGED, listener);
  return () => window.removeEventListener(TEAM_CHANGED, listener);
}
