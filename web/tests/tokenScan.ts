// The token guard's scanner (look & feel redesign P1). It reads stylesheets and component sources as
// text and reports what tokens.test.ts refuses: a colour or a font size written anywhere but the
// token file, and a CSS variable nobody defines. Pure functions, so the test can prove they catch.

export interface Declaration {
  property: string;
  value: string;
  line: number;
}

export interface Finding {
  line: number;
  text: string;
}

const COMMENT = /\/\*[\s\S]*?\*\//g;
const DECLARATION = /([\w-]+)\s*:\s*([^;{}]+)/g;
const HEX = /(?<![\w&-])#[0-9a-f]{3,8}\b/i;
const COLOUR_FUNCTION = /\b(?:rgba?|hsla?|hwb|lab|lch|oklab|oklch|color-mix)\(/i;
const NAMED_COLOUR = /(?<![\w-])(?:white|black)(?![\w-])/i;
const SIZE_TOKEN = /^(?:var\(--fs-[a-z]+\)|inherit)$/;
const LENGTH = /(?<![\w-])\d*\.?\d+(?:px|rem|em|pt|%)/;
const VAR_USE = /var\(\s*(--[\w-]+)/g;
const VAR_DEFINITION = /(--[\w-]+)\s*:/g;
const FONT_SIZE_PROP = /\bfontSize\s*[=:]/;

// Comments become spaces of the same length, so line numbers stay true.
function withoutComments(css: string): string {
  return css.replace(COMMENT, (comment) => comment.replace(/[^\n]/g, " "));
}

export function declarations(css: string): Declaration[] {
  const source = withoutComments(css);
  return [...source.matchAll(DECLARATION)].map((match) => ({
    property: match[1].toLowerCase(),
    value: match[2].trim(),
    line: source.slice(0, match.index).split("\n").length,
  }));
}

export function hardCodedColours(css: string): Declaration[] {
  return declarations(css).filter(({ value }) => HEX.test(value) || COLOUR_FUNCTION.test(value) || NAMED_COLOUR.test(value));
}

export function hardCodedFontSizes(css: string): Declaration[] {
  return declarations(css).filter(({ property, value }) => {
    if (property === "font-size") return !SIZE_TOKEN.test(value);
    if (property === "font") return value !== "inherit" && LENGTH.test(value.replace(/var\([^)]*\)/g, ""));
    return false;
  });
}

export function usedVariables(source: string): Set<string> {
  return new Set([...withoutComments(source).matchAll(VAR_USE)].map((match) => match[1]));
}

export function definedVariables(css: string): Set<string> {
  return new Set([...withoutComments(css).matchAll(VAR_DEFINITION)].map((match) => match[1]));
}

// A component may not carry a colour literal or a fontSize: they belong in the stylesheets.
export function componentLiterals(source: string): Finding[] {
  return source.split("\n").flatMap((text, index) =>
    HEX.test(text) || FONT_SIZE_PROP.test(text) ? [{ line: index + 1, text: text.trim() }] : []);
}

// The declarations of the rule whose selector list holds `selector` (whitespace aside), as property -> value.
export function ruleDeclarations(css: string, selector: string): Map<string, string> {
  const squash = (text: string) => text.replace(/\s+/g, " ").trim();
  const rules = [...withoutComments(css).matchAll(/([^{}]+)\{([^{}]*)\}/g)];
  const rule = rules.find((match) => match[1].split(",").map(squash).includes(squash(selector)));
  return new Map(rule ? declarations(rule[2]).map(({ property, value }) => [property, value]) : []);
}

export function readTokens(css: string): Map<string, string> {
  const block = withoutComments(css).split(":root {")[1]?.split("\n}")[0] ?? "";
  return new Map(declarations(block).filter(({ property }) => property.startsWith("--")).map(({ property, value }) => [property, value]));
}

export function resolveToken(tokens: ReadonlyMap<string, string>, name: string, seen: readonly string[] = []): string {
  const value = tokens.get(name);
  if (value === undefined) throw new Error(`${name} is not a token`);
  if (seen.includes(name)) throw new Error(`${name} refers to itself`);
  const reference = /^var\((--[\w-]+)\)$/.exec(value);
  return reference ? resolveToken(tokens, reference[1], [...seen, name]) : value;
}

function channel(value: number): number {
  const scaled = value / 255;
  return scaled <= 0.03928 ? scaled / 12.92 : ((scaled + 0.055) / 1.055) ** 2.4;
}

function luminance(hex: string): number {
  const match = /^#([0-9a-f]{6})$/i.exec(hex);
  if (!match) throw new Error(`${hex} is not a #rrggbb colour`);
  const number = parseInt(match[1], 16);
  const [red, green, blue] = [(number >> 16) & 255, (number >> 8) & 255, number & 255].map(channel);
  return 0.2126 * red + 0.7152 * green + 0.0722 * blue;
}

// WCAG 2.1 contrast ratio between two #rrggbb colours.
export function contrastRatio(foreground: string, background: string): number {
  const [light, dark] = [luminance(foreground), luminance(background)].sort((a, b) => b - a);
  return (light + 0.05) / (dark + 0.05);
}
