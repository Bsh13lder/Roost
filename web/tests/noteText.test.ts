import { describe, expect, it } from "vitest";
import { parseWikilinks } from "../src/components/notes/wikilink";
import { deriveTitle, normalizePage, plainSnippet, stripFrontMatter } from "../src/components/notes/noteHelpers";

describe("note text helpers", () => {
  it("parses [[target#anchor|display]] links and embeds", () => {
    expect(parseWikilinks("see [[Ana|my friend]] and ![[Garden#roses]]").map((l) => [l.kind, l.target, l.anchor, l.display]))
      .toEqual([["plain", "Ana", "", "my friend"], ["embed", "Garden", "roses", ""]]);
  });

  it("folds a page name the way the server does", () => {
    expect(normalizePage("  Ana   García ")).toBe("ana garcía");
  });

  it("drops a leading front-matter block and nothing else", () => {
    expect(stripFrontMatter("---\ntags: [a]\n---\n# Ana")).toBe("# Ana");
    expect(stripFrontMatter("# Ana\n---\nx")).toBe("# Ana\n---\nx");
  });

  it("derives a title from the first line", () => {
    expect(deriveTitle("Buy milk\nand eggs")).toBe("Buy milk");
  });

  it("shows a list snippet as plain words, not markdown", () => {
    expect(plainSnippet("# Ana Birthday **3 May**, see [[Garden]] and [[Lisbon trip|our trip]]. "
      + "![photo](https://x.example/a.jpg) [her shop](https://shop.example/ana) `code` #people"))
      .toBe("Ana Birthday 3 May, see Garden and our trip. her shop code #people");
  });
});
