import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { TokensLine } from "../src/components/usage/TokensLine";
import { ApiError } from "../src/api/client";
import type { UsageCounts } from "../src/api/usage";

const api = { getUsage: vi.fn() };
vi.mock("../src/api/usage", () => ({ getUsage: (...a: unknown[]) => api.getUsage(...a) }));

const counts = (tokens: number): UsageCounts => ({
  input: tokens, output: 0, cache_read: 0, cache_write: 0, calls: 1, tokens_in: tokens, tokens_out: 0, tokens,
});
const reading = (busiest: { bot_id: string; name: string; tokens: number } | null) => ({
  readable: false, remaining_fraction: null, resets_at: null, days: 7, today: "2026-11-04",
  total: counts(45_000), today_total: counts(1200), per_day: [], bots: [], background: null, busiest,
});
const settle = () => new Promise((resolve) => setTimeout(resolve, 0));

afterEach(() => { cleanup(); api.getUsage.mockReset(); });

describe("TokensLine", () => {
  it("shows today, this week and the busiest bot", async () => {
    api.getUsage.mockResolvedValue(reading({ bot_id: "bot-1", name: "Scout", tokens: 40_000 }));
    render(<TokensLine />);
    expect(await screen.findByText("Tokens today: 1.2k · this week: 45k · busiest: Scout")).toBeInTheDocument();
    expect(api.getUsage).toHaveBeenCalledWith(7);
  });

  it("leaves the busiest bot out when there is none", async () => {
    api.getUsage.mockResolvedValue(reading(null));
    render(<TokensLine />);
    expect(await screen.findByText("Tokens today: 1.2k · this week: 45k")).toBeInTheDocument();
  });

  it("hides itself when the usage can't load", async () => {
    api.getUsage.mockRejectedValue(new ApiError(500, "nope"));
    const { container } = render(<TokensLine />);
    await waitFor(() => expect(api.getUsage).toHaveBeenCalled());
    await settle();
    expect(container).toBeEmptyDOMElement();
  });

  it("hides itself on an older server that sends no totals", async () => {
    api.getUsage.mockResolvedValue({ readable: false, remaining_fraction: null, resets_at: null });
    const { container } = render(<TokensLine />);
    await waitFor(() => expect(api.getUsage).toHaveBeenCalled());
    await settle();
    expect(container).toBeEmptyDOMElement();
  });
});
