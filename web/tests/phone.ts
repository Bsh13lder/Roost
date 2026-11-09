import { afterEach, beforeEach } from "vitest";
import { PHONE_MEDIA } from "../src/components/board/constants";

// jsdom has no layout: this makes window.matchMedia say the phone query matches (or, with `on = false`, nothing does).
export function stubPhone(on = true) {
  const original = window.matchMedia;
  window.matchMedia = ((query: string) => ({
    matches: on && query === PHONE_MEDIA, media: query, onchange: null,
    addListener: () => {}, removeListener: () => {}, addEventListener: () => {}, removeEventListener: () => {},
    dispatchEvent: () => false,
  })) as unknown as typeof window.matchMedia;
  return () => { window.matchMedia = original; };
}

// Installs the phone stub around each test of the calling file.
export function onAPhone() {
  let restore = () => {};
  beforeEach(() => { restore = stubPhone(true); });
  afterEach(() => restore());
}
