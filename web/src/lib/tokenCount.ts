// Token usage in words (docs/plans/2026-11-04-roost-token-usage.md): compact counts, bar heights, Home's line.

const UNITS: ReadonlyArray<{ size: number; suffix: string }> = [
  { size: 1e9, suffix: "B" }, { size: 1e6, suffix: "M" }, { size: 1e3, suffix: "k" },
];
const ROUND_TO = 10; // one decimal
const UNIT_STEP = 1000; // 1000k shows as 1M
const MIN_BAR_PERCENT = 4; // a day that used anything still shows a sliver
const FULL_PERCENT = 100;

const tenths = (value: number): string => {
  const rounded = Math.round(value * ROUND_TO) / ROUND_TO;
  return Number.isInteger(rounded) ? String(rounded) : rounded.toFixed(1);
};

// 999 → "999", 12_340 → "12.3k", 1_234_567 → "1.2M". A value that would round to 1000 of a unit moves up one.
export function compactCount(value: number): string {
  if (!Number.isFinite(value) || value <= 0) return "0";
  const whole = Math.round(value);
  const at = UNITS.findIndex((unit) => whole >= unit.size);
  if (at === -1) return String(whole);
  const unit = UNITS[at];
  const bigger = UNITS[at - 1];
  if (bigger && Math.round((whole / unit.size) * ROUND_TO) / ROUND_TO >= UNIT_STEP) {
    return `${tenths(whole / bigger.size)}${bigger.suffix}`;
  }
  return `${tenths(whole / unit.size)}${unit.suffix}`;
}

// Each day's height as a percent of the busiest day; all zero when nothing was used.
export function barHeights(values: readonly number[]): number[] {
  const max = Math.max(0, ...values);
  if (max <= 0) return values.map(() => 0);
  return values.map((value) => {
    if (value <= 0) return 0;
    return Math.max(MIN_BAR_PERCENT, Math.round((value / max) * FULL_PERCENT));
  });
}

// Home's one line: "Tokens today: 1.2k · this week: 45k · busiest: Scout".
export function tokensLine(today: number, week: number, busiest: string | null): string {
  const line = `Tokens today: ${compactCount(today)} · this week: ${compactCount(week)}`;
  return busiest ? `${line} · busiest: ${busiest}` : line;
}
