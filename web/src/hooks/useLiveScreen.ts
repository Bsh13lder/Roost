import { useCallback, useEffect, useRef, useState, type RefObject } from "react";
import { openLiveSocket } from "../api/live";
import {
  LIVE_CLOSE_ASLEEP, LIVE_CLOSE_GIVEN_BACK, LIVE_CLOSE_NOT_HELD, TOUCH_KEYS, type TouchKey,
} from "../components/computer/constants";
import { loadRfb as defaultLoadRfb, type RfbConstructor, type RfbLike } from "../lib/novnc";

export type LiveScreenState = "connecting" | "live" | "asleep" | "unreachable";

// Hex keysyms for the paste shortcut (X11 Control_L and v).
const KEYSYM_CONTROL_L = 0xffe3;
const KEYSYM_V = 0x76;

export interface UseLiveScreenOptions {
  botId: string;
  target: RefObject<Element | null>;
  mode?: "view" | "control";
  // Control only: the server ended the control socket (given back, or not held any more).
  onControlEnded?: () => void;
  openSocket?: (botId: string, mode?: "view" | "control") => WebSocket;
  loadRfb?: () => Promise<RfbConstructor>;
}

// Text goes to the computer's clipboard and then Ctrl+V into the page; it is never logged or stored here.
function typeInto(rfb: RfbLike, text: string): boolean {
  if (!text || !rfb.clipboardPasteFrom || !rfb.sendKey) return false;
  rfb.clipboardPasteFrom(text);
  rfb.sendKey(KEYSYM_CONTROL_L, "ControlLeft", true);
  rfb.sendKey(KEYSYM_V, "KeyV", true);
  rfb.sendKey(KEYSYM_V, "KeyV", false);
  rfb.sendKey(KEYSYM_CONTROL_L, "ControlLeft", false);
  return true;
}

function pasteInto(rfb: RfbLike, event: Event) {
  if (typeInto(rfb, (event as ClipboardEvent).clipboardData?.getData("text/plain") ?? "")) event.preventDefault();
}

// The live screen: opens the gateway's socket, hands it to noVNC (a lazy chunk) and maps how the socket ends:
// 4410 is asleep, anything else unreachable. In view mode noVNC is view only; in control mode (Take control)
// input goes through, and 4000 or 4409 mean the computer was given back. Unmount closes everything.
export function useLiveScreen({
  botId, target, mode = "view", onControlEnded, openSocket = openLiveSocket, loadRfb = defaultLoadRfb,
}: UseLiveScreenOptions) {
  const [state, setState] = useState<LiveScreenState>("connecting");
  const [attempt, setAttempt] = useState(0);
  const ended = useRef(onControlEnded);
  ended.current = onControlEnded;
  const held = useRef<RfbLike | null>(null); // the control screen's noVNC, for the touch keyboard row
  useEffect(() => {
    let cancelled = false;
    let rfb: RfbLike | null = null;
    let socket: WebSocket | null = null;
    const control = mode === "control";
    const element = target.current;
    const onPaste = (event: Event) => { if (rfb && control) pasteInto(rfb, event); };
    const onClose = (event: Event) => {
      if (cancelled) return;
      const code = (event as CloseEvent).code;
      if (control && (code === LIVE_CLOSE_GIVEN_BACK || code === LIVE_CLOSE_NOT_HELD)) return ended.current?.();
      setState((current) => (current === "asleep" ? current : code === LIVE_CLOSE_ASLEEP ? "asleep" : "unreachable"));
    };
    setState("connecting");
    // The socket opens only once noVNC has loaded: the computer greets at once, and a greeting that arrives
    // before noVNC listens would be lost and the handshake would never start.
    loadRfb()
      .then((Rfb) => {
        if (cancelled || !element) return;
        socket = control ? openSocket(botId, "control") : openSocket(botId);
        socket.addEventListener("close", onClose);
        const screen = new Rfb(element, socket, { shared: true });
        screen.viewOnly = !control;
        screen.scaleViewport = true;
        if (control) { element.addEventListener("paste", onPaste); screen.focus?.(); }
        screen.addEventListener("connect", () => { if (!cancelled) setState("live"); });
        rfb = screen;
        held.current = control ? screen : null;
      })
      .catch(() => { if (!cancelled) setState("unreachable"); });
    return () => {
      cancelled = true;
      held.current = null;
      element?.removeEventListener("paste", onPaste);
      rfb?.disconnect();
      socket?.close();
    };
  }, [botId, mode, attempt, openSocket, loadRfb, target]);
  const retry = useCallback(() => setAttempt((value) => value + 1), []);
  // Control only (a phone has no keyboard for noVNC): text through the clipboard, and one key down and up.
  const typeText = useCallback((text: string) => { if (held.current) typeInto(held.current, text); }, []);
  const pressKey = useCallback((key: TouchKey) => {
    const [keysym, code] = TOUCH_KEYS[key];
    held.current?.sendKey?.(keysym, code, true);
    held.current?.sendKey?.(keysym, code, false);
  }, []);
  return { state, retry, typeText, pressKey };
}
