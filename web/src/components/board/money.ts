// SPDX-License-Identifier: MIT
// Harvested from LazyClaw web/src/components/budgets/money.ts @ 21e1002, adapted for Roost

// Roost amounts are decimal strings ("12.50") from the gateway, which sums them
// with Decimal; here they are only displayed, never added up.
import { dayText } from "../../ui/date/dates";
import { zonedFormat } from "../../lib/timeZone";

// The gateway's limits (roost/constants.py MAX_CATEGORY_NAME_LENGTH,
// MAX_EXPENSE_NOTE_LENGTH): the inputs stop there.
export const MAX_CATEGORY = 40;
export const MAX_NOTE = 200;
export const MAX_AMOUNT_TEXT = 12; // "1000000,00" and a little room

const DEFAULT_CURRENCY = "EUR";
const MONTHS_PER_YEAR = 12;
const CURRENCY_FORMATS = new Map<string, Intl.NumberFormat>();

/** Format an amount with its currency, e.g. `€12.50`, `US$20.00`. */
export function formatMoney(amount: string, currency: string): string {
  const code = currency || DEFAULT_CURRENCY;
  let format = CURRENCY_FORMATS.get(code);
  if (!format) {
    format = new Intl.NumberFormat("en-IE", { style: "currency", currency: code, minimumFractionDigits: 2 });
    CURRENCY_FORMATS.set(code, format);
  }
  return format.format(Number(amount));
}

const SHORT_FORMATS = new Map<string, Intl.NumberFormat>();

/** An amount for a tight column: `€80` for a whole number, `€12.50` otherwise. */
export function formatMoneyShort(amount: string, currency: string): string {
  const code = currency || DEFAULT_CURRENCY;
  const whole = Number(amount) % 1 === 0;
  const key = `${code}:${whole}`;
  let format = SHORT_FORMATS.get(key);
  if (!format) {
    format = new Intl.NumberFormat("en-IE", { style: "currency", currency: code, minimumFractionDigits: whole ? 0 : 2 });
    SHORT_FORMATS.set(key, format);
  }
  return format.format(Number(amount));
}

// "12,50" → "12.50"; anything ambiguous ("1.234,56", 3 decimals, 0) → null.
// The same reading as roost/money/amounts.py, so the form never guesses.
export function parseAmountInput(text: string): string | null {
  let value = text.trim().replace(/US\$|[€$£]/g, "").replace(/\s/g, "");
  if ((value.match(/,/g) ?? []).length === 1 && !value.includes(".")) value = value.replace(",", ".");
  if (!/^\d+(\.\d{1,2})?$/.test(value)) return null;
  const amount = Number(value);
  return amount > 0 ? amount.toFixed(2) : null;
}

export const AMOUNT_HELP = "Enter an amount like 12,50.";

/** A money field that may be left empty: "" → null (none, or clear it); "12,50" → "12.50"; unreadable → undefined. */
export function readAmount(text: string): string | null | undefined {
  if (!text.trim()) return null;
  return parseAmountInput(text) ?? undefined;
}

const monthFormat = () => zonedFormat("en-CA", { year: "numeric", month: "2-digit" });

/** The month ("YYYY-MM") a moment falls in, on the account's calendar. */
export function zoneMonth(date: Date): string {
  const parts = monthFormat().formatToParts(date);
  const part = (type: Intl.DateTimeFormatPartTypes) => parts.find((p) => p.type === type)?.value ?? "";
  return `${part("year")}-${part("month")}`;
}

export function shiftMonth(month: string, delta: number): string {
  const [year, number] = month.split("-").map(Number);
  const index = year * MONTHS_PER_YEAR + (number - 1) + delta;
  return `${Math.floor(index / MONTHS_PER_YEAR)}-${String((index % MONTHS_PER_YEAR) + 1).padStart(2, "0")}`;
}

/** "2026-10" → "October 2026". */
export function monthLabel(month: string): string {
  const [year, number] = month.split("-").map(Number);
  return new Date(Date.UTC(year, number - 1, 15)).toLocaleDateString("en-GB", { month: "long", year: "numeric", timeZone: "UTC" });
}

/** A spent_at day ("2026-10-13", already a day on the account's calendar) → "Tue 13 Oct", with the fixed month names. */
export function dayLabel(day: string): string {
  return dayText(day, { weekday: true });
}

/** An amount in its tight form: `€1,500` for a whole number, `€12.50` otherwise. Formatting only. */
export const formatAmount = formatMoneyShort;

/** `{EUR: "84.20", USD: "12.00"}` → "€84.20 · US$12". Each currency is shown on its own: nothing is added. */
export function currencyList(totals: Readonly<Record<string, string>>, empty = ""): string {
  const parts = Object.entries(totals).map(([code, amount]) => formatAmount(amount, code));
  return parts.length ? parts.join(" · ") : empty;
}

/** "2026-09" → "Sep", with the Board's fixed month names. */
export function monthShort(month: string): string {
  return dayText(`${month}-01`).split(" ")[1] ?? month;
}

/** A signed whole percent: 36 → "+36%", -12 → "-12%", 0 → "0%". */
export function signedPercent(percent: number): string {
  return `${percent > 0 ? "+" : ""}${percent}%`;
}

/** An amount the server sent signed ("-200.20"), without its sign: the overage. */
export function unsigned(amount: string): string {
  return amount.startsWith("-") ? amount.slice(1) : amount;
}

/** A currency's sign as the Board writes it: EUR "€", USD "US$", GBP "£". */
export function currencySign(currency: string): string {
  const parts = new Intl.NumberFormat("en-IE", { style: "currency", currency: currency || DEFAULT_CURRENCY }).formatToParts(0);
  return parts.find((part) => part.type === "currency")?.value ?? currency;
}

const COMPACT_FORMATS = new Map<string, Intl.NumberFormat>();

/** A short scale label: `€4.2K`, `US$153`. Formatting only. */
export function formatCompact(amount: number, currency: string): string {
  const code = currency || DEFAULT_CURRENCY;
  let format = COMPACT_FORMATS.get(code);
  if (!format) {
    format = new Intl.NumberFormat("en-IE", { style: "currency", currency: code, notation: "compact", maximumFractionDigits: 1 });
    COMPACT_FORMATS.set(code, format);
  }
  return format.format(amount);
}
