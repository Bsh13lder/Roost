// The main bundle's budget (M2 D4): the entry chunk may grow by at most
// ~150 KB gzip over its size at the start of M2 — heavy editors load lazily.
// `node scripts/check-bundle.mjs --baseline` records the budget once (M2
// Task 4); `npm run size` checks it after every build.
import { readFileSync, writeFileSync } from "node:fs";
import { gzipSync } from "node:zlib";

const GROWTH_ALLOWED_BYTES = 150 * 1024;
// Code that must stay in a lazy chunk, found by a string only it carries: react-day-picker's class prefix
// (redesign P1) and react-markdown's changelog address (redesign P2).
const LAZY_ONLY_MARKERS = {
  "rdp-": "The calendar (react-day-picker)",
  "remarkjs/react-markdown": "The markdown renderer (react-markdown)",
};
const dist = new URL("../dist/", import.meta.url);
const budgetFile = new URL("../bundle-budget.json", import.meta.url);

function entryGzipBytes() {
  const html = readFileSync(new URL("index.html", dist), "utf8");
  const entry = /<script[^>]+src="\/(assets\/index-[^"]+\.js)"/.exec(html)?.[1];
  if (!entry) throw new Error("No entry script in dist/index.html — run `npm run build` first.");
  const source = readFileSync(new URL(entry, dist));
  return { entry, bytes: gzipSync(source).length, text: source.toString("utf8") };
}

const { entry, bytes, text } = entryGzipBytes();
const leaked = Object.entries(LAZY_ONLY_MARKERS).filter(([marker]) => text.includes(marker));
if (leaked.length > 0) {
  console.error(`${leaked.map(([, what]) => what).join(" and ")} is in the main bundle: import it through React.lazy only.`);
  process.exit(1);
}
if (process.argv.includes("--baseline")) {
  const budget = { baseline_gzip_bytes: bytes, max_gzip_bytes: bytes + GROWTH_ALLOWED_BYTES };
  writeFileSync(budgetFile, `${JSON.stringify(budget, null, 2)}\n`);
  console.log(`baseline ${entry}: ${bytes} B gzip; budget ${budget.max_gzip_bytes} B`);
} else {
  const { max_gzip_bytes: max } = JSON.parse(readFileSync(budgetFile, "utf8"));
  console.log(`entry ${entry}: ${bytes} B gzip (budget ${max} B)`);
  if (bytes > max) {
    console.error("Over the main-bundle budget: load the new code lazily (React.lazy).");
    process.exit(1);
  }
}
