import { createContext, useContext, type ReactNode } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import { linkHost } from "../../lib/linkHost";
import { cx } from "../../ui/cx";
import { CodeBlock } from "./CodeBlock";
import { WIKILINK_PREFIX, wikilinkTarget } from "./markdownLinks";
import { remarkJoinedDomains } from "./remarkJoinedDomains";
import { remarkWikilinks } from "./remarkWikilinks";

// Markdown for bot replies and note previews (redesign P2). The only module that imports react-markdown,
// so it loads as one lazy chunk (web/tests/bundleGuard.test.ts). Safe by construction:
// - raw HTML is never rendered: react-markdown shows it as text;
// - a link's text is its real host (M1), it opens in a new tab with no opener, and only http(s) is a link;
// - an image is never fetched: it shows as "[image: alt]";
// - a [[wikilink]] in prose is a chip: a button where the page can open the note, a plain chip elsewhere;
//   a [[ … ]] in code stays code (remarkWikilinks.ts);
// - its headings sit under the page's own: # is an h3, never the page's h1.
export interface MarkdownProps {
  text: string;
  onWikilink?: (target: string) => void;
  className?: string;
}

type OnWikilink = (target: string) => void;

const PLUGINS = [remarkGfm, remarkJoinedDomains, remarkWikilinks];

// The page's wikilink handler reaches the link component through context, so the component map below is
// one constant. A new map (or a new handler) on each render would give React new element types, and a
// chat row that re-renders on every live frame would remount each table (its scroll), code block (its
// "Copied") and link (its focus).
const WikilinkContext = createContext<OnWikilink | undefined>(undefined);

function MarkdownLink({ href, children }: { href?: string; children?: ReactNode }) {
  const onWikilink = useContext(WikilinkContext);
  if (href?.startsWith(WIKILINK_PREFIX)) {
    const target = wikilinkTarget(href);
    if (target === null) return <span>{children}</span>;
    if (!onWikilink) return <span className="wikilink-chip wikilink-chip--static">{children}</span>;
    return <button type="button" className="wikilink-chip" onClick={() => onWikilink(target)}>{children}</button>;
  }
  const link = linkHost(href);
  if (link === null) return <span>{children}</span>;
  return <a href={link.href} target="_blank" rel="noopener noreferrer" className="md__link">{link.host}</a>;
}

// Never fetched: drawing a reply or a note must not send anything to the host an image names.
function MarkdownImage({ alt }: { alt?: string }) {
  return <span className="md__image">{`[image: ${alt || "untitled"}]`}</span>;
}

// A wide table scrolls inside its own box, never the chat or the page.
function MarkdownTable({ children }: { children?: ReactNode }) {
  return (
    <div className="md__table" role="region" aria-label="Table" tabIndex={0}>
      <table>{children}</table>
    </div>
  );
}

// The page has its own h1 (a bot's name, Board) and h2s, so a screen reader's list of headings keeps the
// page's outline (final-review fix): # is drawn as an h3, ## as an h4, ### as an h5 and deeper ones as an
// h6. Each keeps its own look through its class (md__h1 … md__h6, markdown.css).
const HEADING_TAGS = { h1: "h3", h2: "h4", h3: "h5", h4: "h6", h5: "h6", h6: "h6" } as const;

function shiftedHeading(level: keyof typeof HEADING_TAGS) {
  const Tag = HEADING_TAGS[level];
  return function MarkdownHeading({ children }: { children?: ReactNode }) {
    return <Tag className={`md__${level}`}>{children}</Tag>;
  };
}

const COMPONENTS: Components = {
  a: MarkdownLink, img: MarkdownImage, pre: CodeBlock, table: MarkdownTable,
  h1: shiftedHeading("h1"), h2: shiftedHeading("h2"), h3: shiftedHeading("h3"),
  h4: shiftedHeading("h4"), h5: shiftedHeading("h5"), h6: shiftedHeading("h6"),
};

export default function Markdown({ text, onWikilink, className }: MarkdownProps) {
  return (
    <div className={cx("md", className)}>
      <WikilinkContext value={onWikilink}>
        <ReactMarkdown remarkPlugins={PLUGINS} components={COMPONENTS}>
          {text}
        </ReactMarkdown>
      </WikilinkContext>
    </div>
  );
}
