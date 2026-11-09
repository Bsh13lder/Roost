import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { CloseIcon } from "../components/icons";
import { cx } from "./cx";
import { Button } from "./Button";
import { IconButton } from "./IconButton";
import { TOAST_MS, UNDO_LABEL, UNDO_TOAST_MS } from "./constants";

export type ToastTone = "info" | "ok" | "danger";

export interface ToastOptions {
  tone?: ToastTone;
  duration?: number; // ms; the default is TOAST_MS, or UNDO_TOAST_MS when an action is given
  action?: ToastAction; // a button such as Undo: it runs once, then the note goes
}

export interface ToastAction {
  label: string;
  run: () => void;
}

interface ToastItem {
  id: number;
  message: string;
  tone: ToastTone;
  action?: ToastAction;
}

export interface ToastApi {
  show: (message: string, options?: ToastOptions) => void;
}

const ToastContext = createContext<ToastApi | null>(null);

// The toast queue when there is one above (a part that may also render outside the app's provider, as in a test).
export function useOptionalToast(): ToastApi | null {
  return useContext(ToastContext);
}

export function useToast(): ToastApi {
  const api = useContext(ToastContext);
  if (!api) throw new Error("useToast needs a ToastProvider above it (App.tsx has one).");
  return api;
}

function useToastQueue() {
  const [items, setItems] = useState<readonly ToastItem[]>([]);
  const timers = useRef(new Map<number, number>());
  const next = useRef(0);
  const dismiss = useCallback((id: number) => {
    window.clearTimeout(timers.current.get(id));
    timers.current.delete(id);
    setItems((current) => current.filter((item) => item.id !== id));
  }, []);
  const show = useCallback((message: string, options: ToastOptions = {}) => {
    const id = ++next.current;
    const undo = options.action?.label === UNDO_LABEL;
    // A newer Undo replaces the older one (its own timer then finds nothing to dismiss); other notes stay.
    setItems((current) => [...current.filter((item) => !(undo && item.action?.label === UNDO_LABEL)),
      { id, message, tone: options.tone ?? "info", action: options.action }]);
    const fallback = options.action ? UNDO_TOAST_MS : TOAST_MS;
    timers.current.set(id, window.setTimeout(() => dismiss(id), options.duration ?? fallback));
  }, [dismiss]);
  useEffect(() => {
    const pending = timers.current;
    return () => pending.forEach((timer) => window.clearTimeout(timer));
  }, []);
  return { items, show, dismiss };
}

// Short notes that come and go at the bottom of the screen (redesign P1). One polite live region
// reads each new note once; each note has Dismiss and leaves by itself after its duration. Only the newest
// Undo shows: a newer one replaces the older (lead 01b).
export function ToastProvider({ children }: { children: ReactNode }) {
  const { items, show, dismiss } = useToastQueue();
  const api = useMemo(() => ({ show }), [show]);
  return (
    <ToastContext.Provider value={api}>
      {children}
      <div className="toast-region" role="status" aria-live="polite">
        {items.map((item) => (
          <div key={item.id} className={cx("toast", `toast--${item.tone}`)}>
            <p className="toast__message">{item.message}</p>
            {item.action ? (
              <Button variant="ghost" size="sm" onClick={() => { item.action?.run(); dismiss(item.id); }}>
                {item.action.label}
              </Button>
            ) : null}
            <IconButton label="Dismiss" icon={<CloseIcon />} size="sm" onClick={() => dismiss(item.id)} />
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}
