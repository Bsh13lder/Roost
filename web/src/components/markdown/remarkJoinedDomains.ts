import { splitJoinedDomain } from "../../lib/joinedDomain";
import type { MdNode } from "./remarkWikilinks";

// An autolinked bare host ("www.upwork.com.done") whose last words were glued on by a missing space is cut
// back to the real domain; the glued part becomes plain text after the link. Only a link whose text is its
// own address is touched, never a link a person or bot gave other words.

function bareAddress(url: string): string {
  return url.replace(/^https?:\/\//i, "").replace(/\/$/, "");
}

function splitLink(node: MdNode): MdNode[] {
  const text = node.children?.length === 1 && node.children[0].type === "text" ? node.children[0].value ?? "" : "";
  if (!node.url || !text || text !== bareAddress(node.url) || /[/?#]/.test(text)) return [node];
  const { host, rest } = splitJoinedDomain(text);
  if (!rest) return [node];
  const scheme = /^https?:\/\//i.exec(node.url)?.[0] ?? "https://";
  return [
    { ...node, url: `${scheme}${host}`, children: [{ type: "text", value: host }] },
    { type: "text", value: rest },
  ];
}

export function withTrimmedAutolinks(node: MdNode): MdNode {
  if (!node.children) return node;
  const children = node.children.flatMap((child) => (child.type === "link" ? splitLink(child) : [withTrimmedAutolinks(child)]));
  const changed = children.length !== node.children.length || children.some((child, i) => child !== node.children?.[i]);
  return changed ? { ...node, children } : node;
}

export function remarkJoinedDomains() {
  return (tree: MdNode): MdNode => withTrimmedAutolinks(tree);
}
