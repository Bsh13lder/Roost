import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { FullLimitSwitch } from "../src/components/profile/FullLimitSwitch";
import { ApiError } from "../src/api/client";
import { makeBot } from "./fixtures";

const api = { getUsage: vi.fn(), setFullLimit: vi.fn() };
vi.mock("../src/api/usage", () => ({
  getUsage: (...a: unknown[]) => api.getUsage(...a), setFullLimit: (...a: unknown[]) => api.setFullLimit(...a),
}));
// The "until" times below are fixed, so the clock is too: only Date is faked, so waits and clicks still run.
beforeEach(() => { vi.useFakeTimers({ toFake: ["Date"] }); vi.setSystemTime(new Date("2026-10-21T10:00:00Z")); });
afterEach(() => { cleanup(); vi.useRealTimers(); Object.values(api).forEach((mock) => mock.mockReset()); });

const LABEL = "Use the full limit until it resets";

describe("FullLimitSwitch", () => {
  it("full limit is disabled without a reading", async () => {
    api.getUsage.mockResolvedValue({ readable: false, remaining_fraction: null, resets_at: null });
    render(<FullLimitSwitch bot={makeBot()} onChange={vi.fn()} />);
    expect(await screen.findByText("Roost can't read your usage limit yet, so this stays off.")).toBeInTheDocument();
    expect(screen.getByRole("switch", { name: LABEL })).toBeDisabled();
  });

  it("is disabled when the reading itself fails", async () => {
    api.getUsage.mockRejectedValue(new ApiError(500, "nope"));
    render(<FullLimitSwitch bot={makeBot()} onChange={vi.fn()} />);
    expect(await screen.findByText("Roost can't read your usage limit yet, so this stays off.")).toBeInTheDocument();
  });

  it("full limit shows until when on", async () => {
    api.getUsage.mockResolvedValue({ readable: true, remaining_fraction: 0.6, resets_at: "2026-10-21T20:00:00Z" });
    render(<FullLimitSwitch bot={makeBot({ full_limit_until: "2026-10-21T20:00:00Z" })} onChange={vi.fn()} />);
    expect(await screen.findByText("On until Wed 21 Oct 22:00")).toBeInTheDocument();
    expect(screen.getByRole("switch", { name: LABEL })).toHaveAttribute("aria-checked", "true");
  });

  it("switching on calls PUT and hands the bot back", async () => {
    api.getUsage.mockResolvedValue({ readable: true, remaining_fraction: 0.6, resets_at: null });
    const updated = makeBot({ full_limit_until: "2026-10-21T22:00:00Z" });
    api.setFullLimit.mockResolvedValue(updated);
    const onChange = vi.fn();
    render(<FullLimitSwitch bot={makeBot()} onChange={onChange} />);
    const toggle = await screen.findByRole("switch", { name: LABEL });
    await waitFor(() => expect(toggle).toBeEnabled());
    await userEvent.click(toggle);
    expect(api.setFullLimit).toHaveBeenCalledWith("bot-1", true);
    await waitFor(() => expect(onChange).toHaveBeenCalledWith(updated));
  });
});
