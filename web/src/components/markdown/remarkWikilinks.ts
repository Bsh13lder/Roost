import { iterWikilinks, wikilinkHref, wikilinkLabel } from "../notes/wikilink";

// [[wikilinks]] as chips (M2; the chat since redesign P2), found in the parsed markdown tree rather than in
// the raw text (final-review fix). Only prose text nodes are split, so code is never touched: a fenced,
// indented or inline code's text is its `value`, never a text node. Text inside a link stays as written too,
// since a link cannot hold another. A wikilink becomes a link to "#wikilink/<target>", which Markdown.tsx's
// link component draws as a chip.

// The part of an mdast node this plugin reads and makes.
export interface MdNode {
  type: string;
  value?: string;
  url?: string;
  children?: readonly MdNode[];
}

const NEVER_SPLIT = new Set(["link", "linkReference"]);

function chipsIn(value: string): MdNode[] {
  const parts: MdNode[] = [];
  let at = 0;
  for (const link of iterWikilinks(value)) {
    if (link.start > at) parts.push({ type: "text", value: value.slice(at, link.start) });
    parts.push({ type: "link", url: wikilinkHref(link.target), children: [{ type: "text", value: wikilinkLabel(link) }] });
    at = link.end;
  }
  if (at === 0) return [];
  if (at < value.length) parts.push({ type: "text", value: value.slice(at) });
  return parts;
}

function childParts(child: MdNode): MdNode[] {
  if (child.type !== "text") return [withWikilinkChips(child)];
  const parts = chipsIn(child.value ?? "");
  return parts.length > 0 ? parts : [child];
}

// A copy of `node` with every wikilink in its prose made a link; `node` itself is never edited, and a node
// with no wikilink under it is returned as it is.
export function withWikilinkChips(node: MdNode): MdNode {
  if (!node.children || NEVER_SPLIT.has(node.type)) return node;
  const children = node.children.flatMap(childParts);
  const changed = children.length !== node.children.length || children.some((child, index) => child !== node.children?.[index]);
  return changed ? { ...node, children } : node;
}

// The remark plugin: its transformer returns the new tree, which unified uses in place of the parsed one.
export function remarkWikilinks() {
  return (tree: MdNode): MdNode => withWikilinkChips(tree);
}
