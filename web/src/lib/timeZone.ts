import { useSyncExternalStore } from "react";

// The account's time zone (owner, 2026-11-09: "why not auto detect"): the one place the web keeps it. Every
// date and time the web shows is on this zone's calendar and clock (web/tests/timeZone.test.ts refuses a
// format that does not pass appTimeZone()). Until GET /api/auth/me says otherwise it is the browser's own.

const FALLBACK_ZONE = "UTC";

/** The zone this device is set to, e.g. "America/New_York"; "UTC" when the browser does not say. */
export function browserTimeZone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || FALLBACK_ZONE;
  } catch {
    return FALLBACK_ZONE;
  }
}

/** True for a zone name this browser knows ("Asia/Tokyo", "UTC"); false for anything else. */
export function isTimeZone(name: unknown): name is string {
  if (typeof name !== "string" || !name.trim()) return false;
  try {
    new Intl.DateTimeFormat("en-US", { timeZone: name });
    return true;
  } catch {
    return false;
  }
}

let current = browserTimeZone();
const listeners = new Set<() => void>();
const formats = new Map<string, Intl.DateTimeFormat>();

/** The account's zone, the one every date and time format uses. */
export function appTimeZone(): string {
  return current;
}

/** Switches every format to `zone`; refuses (false) a name the browser does not know. */
export function setAppTimeZone(zone: string): boolean {
  if (!isTimeZone(zone)) return false;
  if (zone === current) return true;
  current = zone;
  listeners.forEach((listener) => listener());
  return true;
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => { listeners.delete(listener); };
}

/** The account's zone, re-rendering the component when it changes. */
export function useAppTimeZone(): string {
  return useSyncExternalStore(subscribe, appTimeZone, appTimeZone);
}

/** An Intl format on the account's zone, made once per zone, locale and options. */
export function zonedFormat(locale: string | undefined, options: Intl.DateTimeFormatOptions): Intl.DateTimeFormat {
  const zone = appTimeZone();
  const key = `${zone}|${locale ?? ""}|${JSON.stringify(options)}`;
  const known = formats.get(key);
  if (known) return known;
  const made = new Intl.DateTimeFormat(locale, { ...options, timeZone: zone });
  formats.set(key, made);
  return made;
}

/** A zone's city as people say it: "America/New_York" → "New York", "UTC" → "UTC". */
export function zoneCity(zone: string): string {
  const last = zone.split("/").pop() ?? zone;
  return last.replace(/_/g, " ");
}

/** Every zone this browser knows, sorted, always with `keep` (the account's and the device's) in it. */
export function supportedTimeZones(keep: readonly string[] = []): string[] {
  const intl = Intl as unknown as { supportedValuesOf?: (key: string) => string[] };
  let known: string[] = [];
  try {
    known = intl.supportedValuesOf ? intl.supportedValuesOf("timeZone") : [];
  } catch {
    known = [];
  }
  return [...new Set([...known, ...keep])].sort();
}
