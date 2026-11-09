// @vitest-environment node
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { contrastRatio, readTokens, resolveToken, ruleDeclarations } from "./tokenScan";

// Review fix (redesign P2): the first block of a reply or a note has no top margin and the last no bottom
// margin. jsdom computes no cascade, so this reads markdown.css: every rule that spaces blocks under .md
// must lose to the edge rules, by lower specificity, or by equal specificity and an earlier place.
const styles = (file: string) => readFileSync(fileURLToPath(new URL(`../src/styles/${file}`, import.meta.url)), "utf8");
const CSS = styles("markdown.css");
const CHAT_CSS = styles("chat.css");
const TOKENS = readTokens(styles("tokens.css"));
const READABLE = 4.5;
// Inline code (never a code block's own code) in a bot's short reply, which is a bubble, not a card.
const BUBBLE_CODE = ".message--bot:not(.message--card) .md :not(pre) > code";
const COMMENT = /\/\*[\s\S]*?\*\//g;
const RULE = /([^{}]+)\{([^{}]*)\}/g;
const VERTICAL_MARGIN = /(?:^|[\s;])margin(?:-top|-bottom)?\s*:/;
const EDGE_RULES = [".md > :first-child", ".md > :last-child"];
// A comma outside parentheses: ".md :is(p, ul), .x" is two selectors, not four.
const TOP_LEVEL_COMMA = /,(?![^()]*\))/;

type Specificity = readonly [number, number, number];

const add = (a: Specificity, b: Specificity): Specificity => [a[0] + b[0], a[1] + b[1], a[2] + b[2]];
const compare = (a: Specificity, b: Specificity): number => a[0] - b[0] || a[1] - b[1] || a[2] - b[2];

// Enough of CSS specificity for this file: :where() adds nothing, :is() and :not() add their most
// specific argument; ids, then classes, attributes and pseudo-classes, then element names and pseudo-elements.
function specificity(selector: string): Specificity {
  const nested: Specificity[] = [];
  const rest = selector.replace(/:where\([^()]*\)/g, " ").replace(/:(?:is|not)\(([^()]*)\)/g, (_, list: string) => {
    nested.push(list.split(",").map((part) => specificity(part.trim())).reduce((a, b) => (compare(a, b) >= 0 ? a : b)));
    return " ";
  });
  const ids = rest.match(/#[\w-]+/g)?.length ?? 0;
  const classes = rest.match(/\.[\w-]+|\[[^\]]*\]|(?<!:):(?!:)[\w-]+/g)?.length ?? 0;
  const names = (rest.replace(/\[[^\]]*\]/g, "").match(/(?:^|[\s>+~])[a-z][\w-]*/gi)?.length ?? 0)
    + (rest.match(/::[\w-]+/g)?.length ?? 0);
  return nested.reduce(add, [ids, classes, names]);
}

interface Rule {
  selector: string;
  body: string;
  order: number;
}

function rules(css: string): Rule[] {
  return [...css.replace(COMMENT, "").matchAll(RULE)].flatMap(([, list, body], order) =>
    list.split(TOP_LEVEL_COMMA).map((selector) => ({ selector: selector.replace(/\s+/g, " ").trim(), body, order })));
}

describe("markdown.css spacing (review fix)", () => {
  it("trims the first block's top margin and the last block's bottom margin", () => {
    expect(ruleDeclarations(CSS, ".md > :first-child").get("margin-top")).toBe("0");
    expect(ruleDeclarations(CSS, ".md > :last-child").get("margin-bottom")).toBe("0");
  });

  it("lets the edge rules beat every rule that spaces blocks under .md", () => {
    const all = rules(CSS);
    const spacing = all.filter((rule) => /^\.md[\s>]/.test(rule.selector) && VERTICAL_MARGIN.test(rule.body)
      && !EDGE_RULES.includes(rule.selector));
    expect(spacing.length).toBeGreaterThan(0);
    const beaten = (edge: Rule, rule: Rule) => {
      const order = compare(specificity(edge.selector), specificity(rule.selector));
      return order > 0 || (order === 0 && edge.order > rule.order);
    };
    for (const edge of all.filter((rule) => EDGE_RULES.includes(rule.selector))) {
      expect(spacing.filter((rule) => !beaten(edge, rule)).map((rule) => rule.selector)).toEqual([]);
    }
  });

  // Final-review fix: in a bot's short bubble (the raised fill) inline code sat on the same raised fill, so it
  // did not read as code. There it takes a fill that stands out from the bubble at least as much as inline code
  // stands out from a long reply's card, with its text still readable.
  it("gives inline code in a bot's bubble a fill that differs from the bubble", () => {
    const fill = (css: string, selector: string): string => {
      const name = /^var\((--[\w-]+)\)$/.exec(ruleDeclarations(css, selector).get("background") ?? "")?.[1];
      if (!name) throw new Error(`${selector} has no token background`);
      return resolveToken(TOKENS, name);
    };
    const bubble = fill(CHAT_CSS, ".message--bot .message__body");
    const card = fill(CHAT_CSS, ".message--card .message__body");
    const codeInCard = fill(CSS, ".md code");
    const codeInBubble = fill(CSS, BUBBLE_CODE);
    expect(codeInBubble).not.toBe(bubble);
    expect(contrastRatio(codeInBubble, bubble)).toBeGreaterThanOrEqual(contrastRatio(codeInCard, card));
    expect(contrastRatio(resolveToken(TOKENS, "--color-text"), codeInBubble)).toBeGreaterThanOrEqual(READABLE);
    // It wins over the plain inline-code rule wherever both match.
    expect(compare(specificity(BUBBLE_CODE), specificity(".md code"))).toBeGreaterThan(0);
  });

  it("reads a rule's selector list as a browser does (the scanner works)", () => {
    expect(rules(".md :is(p, ul), .x > :where(a, b) { margin: 0; }").map((rule) => rule.selector))
      .toEqual([".md :is(p, ul)", ".x > :where(a, b)"]);
  });

  it("scores selectors as a browser does (the scanner works)", () => {
    expect(specificity(".md > :last-child")).toEqual([0, 2, 0]);
    expect(specificity(".md :is(p, ul, .md__code)")).toEqual([0, 2, 0]);
    expect(specificity(".md :where(p, ul, .md__code)")).toEqual([0, 1, 0]);
    expect(specificity(".md li > :is(ul, ol)")).toEqual([0, 1, 2]);
    expect(specificity('.md input[type="checkbox"]')).toEqual([0, 2, 1]);
    expect(specificity("#a .b:focus-visible::before")).toEqual([1, 2, 1]);
  });
});
