// The sidebar loads a bot's threads once per bot. A thread made in place —
// the chat made for a new bot the first time it is opened — is announced here,
// so Layout reloads that bot's threads at once (M2 D6), the way teamChanged
// works for bots.
const THREADS_CHANGED = "roost:threads-changed";

export function announceThreadsChanged(botId: string): void {
  window.dispatchEvent(new CustomEvent<string>(THREADS_CHANGED, { detail: botId }));
}

export function onThreadsChanged(listener: (botId: string) => void): () => void {
  const handler = (event: Event) => listener((event as CustomEvent<string>).detail);
  window.addEventListener(THREADS_CHANGED, handler);
  return () => window.removeEventListener(THREADS_CHANGED, handler);
}
