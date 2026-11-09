import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { Routines } from "../src/pages/Routines";
import type { HubRoutineOut, HubRunOut } from "../src/api/routines";
import { makeBot } from "./fixtures";
import { routine, run } from "./routineFixtures";

const api = {
  listAllRoutines: vi.fn(), listRecentRuns: vi.fn(), listRoutineTemplates: vi.fn(), addTemplate: vi.fn(),
  patchRoutine: vi.fn(), runRoutineNow: vi.fn(), deleteRoutine: vi.fn(),
};
vi.mock("../src/api/routines", () => ({
  listAllRoutines: () => api.listAllRoutines(), listRecentRuns: (n: number) => api.listRecentRuns(n),
  listRoutineTemplates: () => api.listRoutineTemplates(),
  addTemplate: (b: string, t: string) => api.addTemplate(b, t),
  patchRoutine: (...a: unknown[]) => api.patchRoutine(...a), runRoutineNow: (id: string) => api.runRoutineNow(id),
  deleteRoutine: (id: string) => api.deleteRoutine(id),
}));
const scout = makeBot({ id: "bot-1", name: "Scout" });
const quill = makeBot({ id: "bot-2", name: "Quill" });
vi.mock("../src/hooks/useLiveStore", () => ({
  useLiveState: () => ({ routineVersion: { routines: 0 }, bots: { "bot-1": scout, "bot-2": quill } }),
}));

const hubRoutine = (over: Partial<HubRoutineOut> = {}): HubRoutineOut => ({
  ...routine(), bot_id: "bot-1", bot_name: "Scout", next_run_madrid: "2026-10-21T10:07+02:00",
  last_note: null, last_finished_at: null, ...over,
});
const hubRun = (over: Partial<HubRunOut> = {}): HubRunOut => ({
  ...run(), routine_id: "r-1", routine_name: "Morning digest", bot_id: "bot-1", bot_name: "Scout", ...over,
});

const view = () => render(<MemoryRouter><Routines /></MemoryRouter>);

beforeEach(() => {
  api.listAllRoutines.mockResolvedValue([
    hubRoutine({ last_state: "error", last_finished_at: "2026-10-20T08:08:00Z", last_note: "It broke." }),
    hubRoutine({ id: "r-2", name: "Diary", bot_id: "bot-2", bot_name: "Quill" }),
  ]);
  api.listRecentRuns.mockResolvedValue([hubRun()]);
  api.listRoutineTemplates.mockResolvedValue([{
    id: "morning-brief", name: "Morning brief", instructions: "Brief me.",
    schedule: { kind: "times", days: [1], times: ["08:30"] }, words: "Mondays at 08:30", needs_edit: false,
  }]);
});
afterEach(() => { cleanup(); Object.values(api).forEach((mock) => mock.mockReset()); });

describe("Routines page", () => {
  it("lists every bot's routines with the bot, the last result and the switch", async () => {
    view();
    expect(await screen.findByText("Diary")).toBeInTheDocument();
    expect(screen.getByText("Scout · Last: Didn't finish · Tue 20 Oct 10:08 · It broke.")).toBeInTheDocument();
    expect(screen.getByText("Quill")).toBeInTheDocument();
    expect(screen.getByRole("switch", { name: /Diary/ })).toHaveAttribute("aria-checked", "true");
    expect(api.listRecentRuns).toHaveBeenCalledWith(20);
  });

  it("shows recent runs across bots with a link to the run log", async () => {
    view();
    const link = await screen.findByRole("link", { name: "Morning digest" });
    expect(link).toHaveAttribute("href", "/bots/bot-1/routines/r-1/log");
    expect(screen.getByText(/· Scout · Done ·/)).toBeInTheDocument();
  });

  it("adds a template to the bot you pick", async () => {
    api.addTemplate.mockResolvedValue(routine({ id: "r-9", name: "Morning brief" }));
    view();
    expect(await screen.findByText("Mondays at 08:30")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Add Morning brief to a bot" }));
    await userEvent.click(await screen.findByRole("menuitem", { name: "Add to Quill" }));
    expect(api.addTemplate).toHaveBeenCalledWith("bot-2", "morning-brief");
    expect(await screen.findByText("Added “Morning brief” to Quill.")).toBeInTheDocument();
    await waitFor(() => expect(api.listAllRoutines).toHaveBeenCalledTimes(2));
  });

  it("a template that needs your words is added paused and opens in the editor", async () => {
    api.listRoutineTemplates.mockResolvedValue([{
      id: "price-watch", name: "Price watch for a page", instructions: "Open <paste the page address>.",
      schedule: { kind: "times", days: [1], times: ["10:00"] }, words: "Mondays at 10:00", needs_edit: true,
    }]);
    api.addTemplate.mockResolvedValue(routine({
      id: "r-9", name: "Price watch for a page", instructions: "Open <paste the page address>.", enabled: false,
    }));
    view();
    expect(await screen.findByText("Paused until you fill it in")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Add Price watch for a page to a bot" }));
    await userEvent.click(await screen.findByRole("menuitem", { name: "Add to Quill" }));
    expect(api.addTemplate).toHaveBeenCalledWith("bot-2", "price-watch");
    expect(await screen.findByText(
      "Added “Price watch for a page” to Quill, paused. Fill in its instructions, then switch it on.")).toBeInTheDocument();
    expect(await screen.findByRole("dialog", { name: "Edit routine" })).toBeInTheDocument();
    expect(screen.getByDisplayValue("Open <paste the page address>.")).toBeInTheDocument();
  });

  it("says when a template can't be added", async () => {
    api.addTemplate.mockRejectedValue(new Error("This bot already has 20 routines."));
    view();
    await userEvent.click(await screen.findByRole("button", { name: "Add Morning brief to a bot" }));
    await userEvent.click(await screen.findByRole("menuitem", { name: "Add to Scout" }));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });

  it("an empty list says how to start", async () => {
    api.listAllRoutines.mockResolvedValue([]);
    api.listRecentRuns.mockResolvedValue([]);
    view();
    expect(await screen.findByText("No routines yet. Add one from a template below.")).toBeInTheDocument();
    expect(screen.getByText("No runs yet.")).toBeInTheDocument();
  });
});
