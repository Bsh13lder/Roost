// A link as it may be drawn: the hostname it shows and the absolute address it opens.
export interface LinkTarget {
  readonly host: string;
  readonly href: string;
}

// M1's link-safety rule in one place, shared by the chat's plain text (chat/PlainText.tsx), the markdown
// renderer (markdown/Markdown.tsx) and the Stuck card (lib/stuck.ts): a link shows its real hostname, never
// text a bot or a note chose for it, and only an absolute http(s) URL is a link. Its href is the parsed URL,
// never the raw string: "http:bank.example/login" names bank.example, but a browser resolves that raw string
// against this page (http://127.0.0.1:18800/bank.example/login), so the shown host and the target would differ.
export function linkHost(href: string | undefined): LinkTarget | null {
  if (!href) return null;
  try {
    const url = new URL(href);
    if (url.protocol !== "http:" && url.protocol !== "https:") return null;
    return { host: url.hostname, href: url.href };
  } catch {
    return null;
  }
}
