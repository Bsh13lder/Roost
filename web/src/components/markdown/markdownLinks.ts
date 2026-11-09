// [[wikilinks]] inside markdown (M2, shared by the notes preview and the chat since redesign P2). They are
// found in the parsed tree (remarkWikilinks.ts) and reach the link component as "#wikilink/<target>".
export const WIKILINK_PREFIX = "#wikilink/";

// A hand-typed "#wikilink/%E0%A4" can't be decoded: plain text, never a crash.
export function wikilinkTarget(href: string): string | null {
  try {
    return decodeURIComponent(href.slice(WIKILINK_PREFIX.length).split("#")[0]);
  } catch {
    return null;
  }
}
