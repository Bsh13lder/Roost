import { linkHost, type LinkTarget } from "../../lib/linkHost";

// Splits a message body into plain-text segments and http(s) links. A
// link renders as its real hostname (never the raw URL or any text the
// bot supplied for it) and opens the parsed address that hostname names,
// so a bot can't disguise where a link actually goes — this is also why
// remote images are never rendered at all: the body is plain text, there
// is no markdown image syntax or <img> path here.
const LINK_PATTERN = /https?:\/\/[^\s<>"')]+/g;

export function renderBody(body: string, keyPrefix: string) {
  const parts: Array<string | LinkTarget> = [];
  let lastIndex = 0;
  for (const match of body.matchAll(LINK_PATTERN)) {
    const url = match[0];
    const start = match.index ?? 0;
    if (start > lastIndex) parts.push(body.slice(lastIndex, start));
    parts.push(linkHost(url) ?? url);
    lastIndex = start + url.length;
  }
  if (lastIndex < body.length) parts.push(body.slice(lastIndex));

  return parts.map((part, index) => {
    const key = `${keyPrefix}-${index}`;
    if (typeof part === "string") return <span key={key}>{part}</span>;
    return (
      <a key={key} href={part.href} target="_blank" rel="noopener noreferrer" className="message__link">
        {part.host}
      </a>
    );
  });
}

// A body as written (redesign P2): your own messages, notices, and a bot's reply while the markdown
// renderer loads, or if it never does. Its line breaks are kept (styles/chat.css).
export function PlainText({ text, keyPrefix }: { text: string; keyPrefix: string }) {
  return <span className="message__plain">{renderBody(text, keyPrefix)}</span>;
}
