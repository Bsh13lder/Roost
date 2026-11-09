// @vitest-environment node
import { describe, expect, it } from "vitest";
import { remarkWikilinks, withWikilinkChips, type MdNode } from "../src/components/markdown/remarkWikilinks";

// Final-review fix: [[wikilinks]] become links in the parsed tree, so code (whose text is a value, never a
// text node) and links are never touched, and the tree it is given is never edited.
const text = (value: string): MdNode => ({ type: "text", value });

describe("remarkWikilinks", () => {
  it("splits a text node around each wikilink, as a link the renderer draws as a chip", () => {
    const tree: MdNode = { type: "root", children: [{ type: "paragraph", children: [text("See [[Ana|my friend]] and ![[Garden#roses]].")] }] };
    expect(withWikilinkChips(tree)).toEqual({ type: "root", children: [{ type: "paragraph", children: [
      text("See "),
      { type: "link", url: "#wikilink/Ana", children: [text("my friend")] },
      text(" and "),
      { type: "link", url: "#wikilink/Garden", children: [text("Garden")] },
      text("."),
    ] }] });
  });

  it("leaves code, inline code and links alone, and never edits the tree it is given", () => {
    const tree: MdNode = { type: "root", children: [
      { type: "code", value: "if [[ -f x ]]; then echo; fi" },
      { type: "paragraph", children: [
        { type: "inlineCode", value: 'df[["a"]]' },
        { type: "link", url: "https://docs.example", children: [text("[[Ana]]")] },
      ] },
    ] };
    const before = structuredClone(tree);
    expect(withWikilinkChips(tree)).toEqual(before);
    expect(tree).toEqual(before);
  });

  it("returns the same node when nothing under it changes", () => {
    const tree: MdNode = { type: "root", children: [{ type: "paragraph", children: [text("no links here")] }] };
    expect(withWikilinkChips(tree)).toBe(tree);
  });

  it("is a remark plugin: its transformer returns the new tree", () => {
    const tree: MdNode = { type: "root", children: [text("[[Ana]]")] };
    expect(remarkWikilinks()(tree)).toEqual({ type: "root", children: [{ type: "link", url: "#wikilink/Ana", children: [text("Ana")] }] });
  });
});
