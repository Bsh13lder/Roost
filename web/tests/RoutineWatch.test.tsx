import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { RoutineEditor } from "../src/components/routines/RoutineEditor";
import { watchLine } from "../src/components/routines/RoutineRow";
import { zoneClock } from "../src/components/routines/zoneTime";
import { watchIn } from "../src/components/routines/WatchFields";
import { routine } from "./routineFixtures";

const api = { createRoutine: vi.fn(), patchRoutine: vi.fn(), previewSchedule: vi.fn() };
vi.mock("../src/api/routines", () => ({
  createRoutine: (...a: unknown[]) => api.createRoutine(...a), patchRoutine: (...a: unknown[]) => api.patchRoutine(...a),
  previewSchedule: (...a: unknown[]) => api.previewSchedule(...a),
}));
const standing = { listPermissions: vi.fn() };
vi.mock("../src/api/standing", () => ({ listPermissions: (...a: unknown[]) => standing.listPermissions(...a) }));

afterEach(() => { cleanup(); Object.values(api).forEach((mock) => mock.mockReset()); standing.listPermissions.mockReset(); });

const PREVIEW = { words: "Weekdays at 09:00", next: ["2026-10-21T09:00:00+02:00"] };
const WATCH = {
  url: "https://web.whatsapp.com/", part: "the physio chat", every_min: 5, host: "web.whatsapp.com",
  last_checked_at: "2026-11-04T13:55:00Z", last_changed_at: "2026-11-04T13:50:00Z",
};

describe("Only run when the page changes", () => {
  it("the switch shows the address, the part and the minutes, hides the schedule and sends the watch", async () => {
    api.previewSchedule.mockResolvedValue(PREVIEW);
    api.createRoutine.mockResolvedValue(routine());
    render(<RoutineEditor botId="bot-1" routine={null} onClose={vi.fn()} onSaved={vi.fn()} />);
    expect(screen.queryByLabelText("Page address")).not.toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Name"), "Physio");
    await userEvent.type(screen.getByLabelText("What to do"), "Tell me what Ana wrote");
    await userEvent.click(screen.getByRole("switch", { name: "Only run when the page changes" }));
    expect(screen.queryByRole("button", { name: "Mon" })).not.toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Page address"), "https://web.whatsapp.com");
    await userEvent.type(screen.getByLabelText(/What part to watch/), "the physio chat");
    const every = screen.getByLabelText("Check every (minutes)");
    await userEvent.clear(every);
    await userEvent.type(every, "10");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(api.createRoutine).toHaveBeenCalled());
    expect(api.createRoutine).toHaveBeenLastCalledWith("bot-1", expect.objectContaining({
      name: "Physio", watch: { url: "https://web.whatsapp.com", part: "the physio chat", every_min: 10 },
    }));
  });

  it("switching an existing watch off sends null; a refusal shows the server's sentence", async () => {
    api.previewSchedule.mockResolvedValue(PREVIEW);
    standing.listPermissions.mockResolvedValue([]);
    api.patchRoutine.mockRejectedValueOnce(Object.assign(new Error("x"), { status: 422, detail: "nope" }));
    api.patchRoutine.mockResolvedValue(routine());
    const onSaved = vi.fn();
    render(<RoutineEditor botId="bot-1" routine={routine({ watch: WATCH })} onClose={vi.fn()} onSaved={onSaved} />);
    expect(screen.getByLabelText("Page address")).toHaveValue("https://web.whatsapp.com/");
    await userEvent.click(screen.getByRole("switch", { name: "Only run when the page changes" }));
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(onSaved).toHaveBeenCalled());
    expect(api.patchRoutine).toHaveBeenLastCalledWith("r-1", expect.objectContaining({ watch: null }));
  });

  it("the row says what it watches, how often and when it last changed", () => {
    const now = new Date("2026-11-04T15:00:00Z");
    expect(zoneClock(WATCH.last_changed_at, now)).toBe("14:50");
    expect(zoneClock("2026-11-02T13:50:00Z", now)).toBe("Mon 2 Nov 14:50");
    expect(zoneClock(null, now)).toBe("");
    expect(watchLine(routine({ watch: { ...WATCH, last_changed_at: null } }))).toBe("Watching web.whatsapp.com · every 5 min");
    expect(watchLine(routine())).toBe("");
  });

  it("a watch with no minutes typed falls back to the default", () => {
    expect(watchIn({ on: true, url: " https://x.com ", part: "", every: "" })).toEqual({ url: "https://x.com", part: "", every_min: 5 });
    expect(watchIn({ on: false, url: "x", part: "", every: "5" })).toBeNull();
  });
});
