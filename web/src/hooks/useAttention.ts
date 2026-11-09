import { useCallback, useEffect, useState, useSyncExternalStore } from "react";
import {
  askNotificationPermission, attentionFor, attentionSnapshot, markAttention, notificationPermission,
  onAttentionChange, showNotification, type BrowserPermission,
} from "../lib/attention";
import { onLiveFrame } from "./useLiveStore";

export function useAttention(): ReadonlySet<string> {
  return useSyncExternalStore(onAttentionChange, attentionSnapshot);
}

// The browser's permission, and a one-tap ask (from a click) that updates it.
export function useNotificationPermission(): [BrowserPermission, () => Promise<void>] {
  const [permission, setPermission] = useState(notificationPermission);
  const ask = useCallback(async () => setPermission(await askNotificationPermission()), []);
  return [permission, ask];
}

// Mounted once, in Layout: while the tab is hidden, a bot with notifications
// on that finishes a reply, turns Asking you or gets Stuck is highlighted and notified.
export function useAttentionNotifications(): void {
  useEffect(() => onLiveFrame((frame, state) => {
    if (document.visibilityState !== "hidden") return;
    const signal = attentionFor(frame, state.bots);
    if (!signal) return;
    markAttention(signal.botId);
    showNotification(signal);
  }), []);
}
