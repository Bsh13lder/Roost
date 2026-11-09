import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import UsageSection from "../src/components/usage/UsageSection";
import { ApiError } from "../src/api/client";
import type { BotUsageOut, UsageCounts, UsageDay } from "../src/api/usage";

const api = { getBotUsage: vi.fn() };
vi.mock("../src/api/usage", () => ({ getBotUsage: (...a: unknown[]) => api.getBotUsage(...a) }));

const counts = (input: number, output: number): UsageCounts => ({
  input, output, cache_read: 0, cache_write: 0, calls: 1, tokens_in: input, tokens_out: output, tokens: input + output,
});
const day = (d: string, input: number, output: number): UsageDay => ({ day: d, ...counts(input, output) });
const DAYS = ["2026-10-29", "2026-10-30", "2026-10-31", "2026-11-01", "2026-11-02", "2026-11-03", "2026-11-04"];

function usage(perDay: UsageDay[]): BotUsageOut {
  const input = perDay.reduce((sum, d) => sum + d.tokens_in, 0);
  const output = perDay.reduce((sum, d) => sum + d.tokens_out, 0);
  return { bot_id: "bot-1", days: 7, today: "2026-11-04", total: counts(input, output),
    today_total: counts(perDay[6].tokens_in, perDay[6].tokens_out), per_day: perDay };
}

beforeEach(() => {
  api.getBotUsage.mockResolvedValue(usage(DAYS.map((d, i) => day(d, i * 1000, i * 100))));
});
afterEach(() => { cleanup(); api.getBotUsage.mockReset(); });

describe("UsageSection", () => {
  it("shows today, the last 7 days and in · out", async () => {
    render(<UsageSection botId="bot-1" />);
    expect(api.getBotUsage).toHaveBeenCalledWith("bot-1", 7);
    expect(await screen.findByText("6.6k tokens")).toBeInTheDocument(); // today: 6000 + 600
    expect(screen.getByText("23.1k tokens")).toBeInTheDocument(); // the week: 21000 + 2100
    expect(screen.getByText("in 21k · out 2.1k")).toBeInTheDocument();
  });

  it("draws one labelled bar per day", async () => {
    render(<UsageSection botId="bot-1" />);
    const bars = await screen.findAllByRole("img");
    expect(bars).toHaveLength(7);
    expect(bars[6]).toHaveAccessibleName("2026-11-04: 6.6k tokens");
    expect(bars[0]).toHaveAccessibleName("2026-10-29: 0 tokens");
  });

  it("says so when the bot has used nothing yet", async () => {
    api.getBotUsage.mockResolvedValue(usage(DAYS.map((d) => day(d, 0, 0))));
    render(<UsageSection botId="bot-1" />);
    expect(await screen.findByText("No tokens used yet.")).toBeInTheDocument();
    expect(screen.queryAllByRole("img")).toHaveLength(0);
  });

  it("shows a friendly error when the usage can't load", async () => {
    api.getBotUsage.mockRejectedValue(new ApiError(500, "Usage is down"));
    render(<UsageSection botId="bot-1" />);
    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });
});
