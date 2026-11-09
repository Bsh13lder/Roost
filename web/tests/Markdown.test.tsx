import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import Markdown from "../src/components/markdown/Markdown";
import { hastText } from "../src/components/markdown/CodeBlock";

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

// A bot's reply as the model writes it: a heading, a list, a [[wikilink]], a table, a code block and links.
const REPLY = [
  "## Your week",
  "",
  "- **Monday**: dentist",
  "- Tue: [[Garden plan]]",
  "",
  "| Day | Task |",
  "| --- | --- |",
  "| Mon | Dentist |",
  "",
  "```",
  "npm run build",
  "```",
  "",
  "See https://example.com/a/b and [the docs](https://docs.example/guide).",
].join("\n");

describe("Markdown (redesign P2)", () => {
  it("draws headings, lists, a table in its own scroll box and a code block", () => {
    const { container } = render(<Markdown text={REPLY} />);
    expect(screen.getByRole("heading", { level: 4, name: "Your week" })).toBeInTheDocument();
    expect(screen.getByText("Monday").tagName).toBe("STRONG");
    const table = screen.getByRole("region", { name: "Table" });
    expect(within(table).getByRole("table")).toBeInTheDocument();
    expect(table).toHaveAttribute("tabindex", "0");
    expect(container.querySelector(".md__code pre code")).toHaveTextContent("npm run build");
  });

  it("shows each link as its real host, opening in a new tab with no opener", () => {
    render(<Markdown text={REPLY} />);
    const docs = screen.getByRole("link", { name: "docs.example" });
    expect(docs).toHaveAttribute("href", "https://docs.example/guide");
    expect(docs).toHaveAttribute("target", "_blank");
    expect(docs).toHaveAttribute("rel", "noopener noreferrer");
    expect(screen.getByRole("link", { name: "example.com" })).toHaveAttribute("href", "https://example.com/a/b");
    expect(screen.queryByText("the docs")).toBeNull();
  });

  it("draws a [[wikilink]] as a chip: a plain chip in chat, a button where a note can open", async () => {
    const { unmount } = render(<Markdown text={REPLY} />);
    expect(screen.getByText("Garden plan")).toHaveClass("wikilink-chip", "wikilink-chip--static");
    expect(screen.queryByRole("button", { name: "Garden plan" })).toBeNull();
    unmount();
    const onWikilink = vi.fn();
    render(<Markdown text={REPLY} onWikilink={onWikilink} />);
    await userEvent.click(screen.getByRole("button", { name: "Garden plan" }));
    expect(onWikilink).toHaveBeenCalledWith("Garden plan");
  });

  it("copies a code block's text, and says so", async () => {
    const user = userEvent.setup();
    render(<Markdown text={REPLY} />);
    await user.click(screen.getByRole("button", { name: "Copy code" }));
    expect(await navigator.clipboard.readText()).toBe("npm run build");
    expect(screen.getByRole("button", { name: "Copied" })).toBeInTheDocument();
  });

  it("says Copy failed when the browser refuses the clipboard", async () => {
    const user = userEvent.setup();
    vi.spyOn(navigator.clipboard, "writeText").mockRejectedValue(new DOMException("Denied", "NotAllowedError"));
    render(<Markdown text={REPLY} />);
    await user.click(screen.getByRole("button", { name: "Copy code" }));
    expect(await screen.findByRole("button", { name: "Copy failed" })).toBeInTheDocument();
  });

  // Review Focus 1: a reply written after reading a hostile page.
  it("renders a hostile reply safely: no raw HTML, no script link, no remote image, real hosts only", () => {
    const hostile = [
      '<img src="https://evil.example/x.png" onerror="alert(1)"> <script>alert(2)</script>',
      "",
      "[Your bank](https://phish.example/login) and [run me](javascript:alert(3))",
      "",
      "![tracker](https://evil.example/pixel.png)",
    ].join("\n");
    const { container } = render(<Markdown text={hostile} />);
    expect(container.querySelector("img, script, iframe")).toBeNull();
    expect(container).toHaveTextContent('<img src="https://evil.example/x.png" onerror="alert(1)">');
    expect(screen.getAllByRole("link")).toHaveLength(1);
    expect(screen.getByRole("link", { name: "phish.example" })).toHaveAttribute("href", "https://phish.example/login");
    expect(screen.queryByText("Your bank")).toBeNull();
    expect(screen.getByText("run me").tagName).toBe("SPAN");
    expect(screen.getByText("[image: tracker]")).toBeInTheDocument();
  });

  // Review fix: the href is the parsed absolute URL. A raw "http:bank.example/login" would show bank.example
  // but resolve against this page (http://127.0.0.1:18800/bank.example/login).
  it("sends a link to the address its shown host names, never one resolved against this page", () => {
    const tricky = [
      "[Your bank](http:bank.example/login), <http:evil.example>, [a ref][r] and [slash](http:/one.example/x)",
      "",
      "[home](/bots/x) and [proto](//evil.example/x)",
      "",
      "[r]: http:ref.example/path",
    ].join("\n");
    render(<Markdown text={tricky} />);
    expect(screen.getByRole("link", { name: "bank.example" })).toHaveAttribute("href", "http://bank.example/login");
    expect(screen.getByRole("link", { name: "evil.example" })).toHaveAttribute("href", "http://evil.example/");
    expect(screen.getByRole("link", { name: "ref.example" })).toHaveAttribute("href", "http://ref.example/path");
    expect(screen.getByRole("link", { name: "one.example" })).toHaveAttribute("href", "http://one.example/x");
    expect(screen.getAllByRole("link")).toHaveLength(4);
    expect(screen.getByText("home").tagName).toBe("SPAN");
    expect(screen.getByText("proto").tagName).toBe("SPAN");
  });

  // Review fix: a chat row re-renders on every live frame, so a reply's blocks must stay the same nodes:
  // a table keeps its scroll, a code block its "Copied", and a link its keyboard focus.
  it("keeps tables, code blocks and links mounted across a re-render with the same props", async () => {
    const user = userEvent.setup();
    const { rerender } = render(<Markdown text={REPLY} />);
    const table = screen.getByRole("region", { name: "Table" });
    table.scrollLeft = 40;
    await user.click(screen.getByRole("button", { name: "Copy code" }));
    const copied = screen.getByRole("button", { name: "Copied" });
    const link = screen.getByRole("link", { name: "docs.example" });
    link.focus();
    rerender(<Markdown text={REPLY} />);
    expect(screen.getByRole("region", { name: "Table" })).toBe(table);
    expect(screen.getByRole("region", { name: "Table" }).scrollLeft).toBe(40);
    expect(screen.getByRole("button", { name: "Copied" })).toBe(copied);
    expect(screen.getByRole("link", { name: "docs.example" })).toBe(link);
    expect(link).toHaveFocus();
  });

  it("keeps a wikilink chip mounted when the page passes a new handler each render, and calls the newest", async () => {
    const user = userEvent.setup();
    const first = vi.fn();
    const latest = vi.fn();
    const { rerender } = render(<Markdown text={REPLY} onWikilink={(target) => first(target)} />);
    const chip = screen.getByRole("button", { name: "Garden plan" });
    chip.focus();
    rerender(<Markdown text={REPLY} onWikilink={(target) => latest(target)} />);
    expect(screen.getByRole("button", { name: "Garden plan" })).toBe(chip);
    expect(chip).toHaveFocus();
    await user.click(chip);
    expect(latest).toHaveBeenCalledWith("Garden plan");
    expect(first).not.toHaveBeenCalled();
  });

  // Final-review fix: a [[ … ]] in code is code. Only prose turns into chips.
  it("leaves [[ ]] in a code block as written, and Copy code copies it as written", async () => {
    const user = userEvent.setup();
    const script = 'if [[ -f "$file" ]]; then\n  echo "[[Garden plan]]"\nfi';
    const { container } = render(<Markdown text={["```bash", script, "```"].join("\n")} />);
    expect(container.querySelector(".md__code pre code")?.textContent).toBe(`${script}\n`);
    expect(container.querySelector(".wikilink-chip, a")).toBeNull();
    await user.click(screen.getByRole("button", { name: "Copy code" }));
    expect(await navigator.clipboard.readText()).toBe(script);
  });

  it("leaves [[ ]] in an indented code block and in inline code as written", () => {
    const text = 'Pick columns with `df[["a", "b"]]` or rows with `a[[0, 1]]`.\n\n    matrix = [[1, 2], [3, 4]]';
    const { container } = render(<Markdown text={text} />);
    const codes = [...container.querySelectorAll("code")].map((code) => code.textContent);
    expect(codes).toEqual(['df[["a", "b"]]', "a[[0, 1]]", "matrix = [[1, 2], [3, 4]]\n"]);
    expect(container.querySelector(".wikilink-chip, a")).toBeNull();
  });

  it("still draws a [[wikilink]] in prose as a chip: labelled, in a heading, or with a parenthesis", () => {
    const onWikilink = vi.fn();
    const text = "# About [[Garden plan]]\n\nSee [[Ana|my friend]], [[Smile :)]] and `[[not a chip]]`.";
    render(<Markdown text={text} onWikilink={onWikilink} />);
    expect(screen.getAllByRole("button").map((chip) => chip.textContent)).toEqual(["Garden plan", "my friend", "Smile :)"]);
    screen.getAllByRole("button").forEach((chip) => chip.click());
    expect(onWikilink.mock.calls).toEqual([["Garden plan"], ["Ana"], ["Smile :)"]]);
    expect(screen.getByText("[[not a chip]]").tagName).toBe("CODE");
  });

  it("never draws a chip inside a link", () => {
    render(<Markdown text="[see [[Garden plan]]](https://docs.example/x)" />);
    expect(screen.getByRole("link", { name: "docs.example" })).toBeInTheDocument();
    expect(document.querySelector(".wikilink-chip")).toBeNull();
  });

  // Final-review fix: the page keeps its own outline. A reply's or a note's headings sit under the page's h1
  // (and any h2): # is an h3, ## an h4, ### an h5, and deeper ones h6, each keeping its own size.
  it("draws headings below the page's own, keeping their sizes", () => {
    const text = ["# One", "## Two", "### Three", "#### Four", "###### Six"].join("\n\n");
    const { container } = render(<Markdown text={text} />);
    const levels = screen.getAllByRole("heading").map((heading) => [heading.tagName, heading.className, heading.textContent]);
    expect(levels).toEqual([
      ["H3", "md__h1", "One"], ["H4", "md__h2", "Two"], ["H5", "md__h3", "Three"], ["H6", "md__h4", "Four"], ["H6", "md__h6", "Six"],
    ]);
    expect(container.querySelector("h1, h2")).toBeNull();
  });

  it("reads a code block's text from its tree", () => {
    const pre = { type: "element", children: [{ type: "element", children: [{ type: "text", value: "a\nb\n" }] }] };
    expect(hastText(pre)).toBe("a\nb\n");
    expect(hastText(undefined)).toBe("");
  });
});

describe("a link that swallowed the next word", () => {
  it("links www.upwork.com only, with 'done' outside the link", () => {
    for (const text of [
      "On it: opening www.upwork.com.done: all set",
      "On it: opening [www.upwork.com.done](https://www.upwork.com.done)",
    ]) {
      const { container, unmount } = render(<Markdown text={text} />);
      const link = screen.getByRole("link");
      expect(link).toHaveAttribute("href", expect.stringMatching(/^https?:\/\/www\.upwork\.com\/$/));
      expect(link).toHaveTextContent("www.upwork.com");
      expect(link).not.toHaveTextContent("done");
      expect(container).toHaveTextContent(/\.done/);
      unmount();
    }
  });

  it("leaves real multi-label hosts alone", () => {
    render(<Markdown text="see www.bbc.co.uk and example.com.au and https://a.com/x" />);
    expect(screen.getByRole("link", { name: "www.bbc.co.uk" })).toBeInTheDocument();
  });
});
