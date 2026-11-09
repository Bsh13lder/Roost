import { describe, expect, it } from "vitest";
import {
  currencyList, dayLabel, formatMoney, zoneMonth, monthLabel, monthShort, parseAmountInput, shiftMonth, signedPercent,
  unsigned,
} from "../src/components/board/money";

describe("money helpers", () => {
  it("reads a Spanish comma decimal and refuses what it can't read", () => {
    expect(parseAmountInput("12,50")).toBe("12.50");
    expect(parseAmountInput(" 12.5 ")).toBe("12.50");
    expect(parseAmountInput("€ 7")).toBe("7.00");
    expect(parseAmountInput("1.234,56")).toBeNull();
    expect(parseAmountInput("12.505")).toBeNull();
    expect(parseAmountInput("0")).toBeNull();
    expect(parseAmountInput("abc")).toBeNull();
    expect(parseAmountInput("")).toBeNull();
  });

  it("formats an amount with its currency", () => {
    expect(formatMoney("12.50", "EUR")).toContain("12.50");
    expect(formatMoney("12.50", "EUR")).toContain("€");
    expect(formatMoney("20.00", "USD")).toContain("20.00");
  });

  it("months are Madrid months and shift across years", () => {
    expect(zoneMonth(new Date("2026-10-31T23:30:00Z"))).toBe("2026-11");
    expect(zoneMonth(new Date("2026-10-31T21:30:00Z"))).toBe("2026-10");
    expect(shiftMonth("2026-01", -1)).toBe("2025-12");
    expect(shiftMonth("2026-12", 1)).toBe("2027-01");
    expect(monthLabel("2026-10")).toBe("October 2026");
  });

  it("names a spent day without moving it to another day", () => {
    expect(dayLabel("2026-10-13")).toBe("Tue 13 Oct");
    expect(dayLabel("2026-09-15")).toBe("Tue 15 Sep"); // ICU's en-GB says "Sept"
    expect(dayLabel("not a day")).toBe("not a day");
  });
});

describe("the Money tab's formatting (G8)", () => {
  it("lists each currency apart, whole amounts without decimals", () => {
    expect(currencyList({ EUR: "84.20", USD: "12.00" })).toBe("€84.20 · US$12");
    expect(currencyList({}, "€0.00")).toBe("€0.00");
  });

  it("names a month by its fixed short name", () => {
    expect(monthShort("2026-09")).toBe("Sep");
    expect(monthShort("2026-12")).toBe("Dec");
  });

  it("signs a percent and strips the sign of an overage", () => {
    expect([signedPercent(36), signedPercent(-12), signedPercent(0)]).toEqual(["+36%", "-12%", "0%"]);
    expect(unsigned("-200.20")).toBe("200.20");
    expect(unsigned("5.00")).toBe("5.00");
  });
});

describe("parseAmountInput signs (Task 7)", () => {
  it("reads $12 and £5", () => {
    expect(parseAmountInput("$12")).toBe("12.00");
    expect(parseAmountInput("£5,50")).toBe("5.50");
    expect(parseAmountInput("US$ 7")).toBe("7.00");
  });
});
