import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { RoutinesCard } from "../src/components/routines/RoutinesCard";
import { routine, run } from "./routineFixtures";

const api = {
  listRoutines: vi.fn(), patchRoutine: vi.fn(), deleteRoutine: vi.fn(), runRoutineNow: vi.fn(), listRuns: vi.fn(),
  createRoutine: vi.fn(), previewSchedule: vi.fn(),
};
vi.mock("../src/api/routines", () => ({
  listRoutines: (...a: unknown[]) => api.listRoutines(...a), patchRoutine: (...a: unknown[]) => api.patchRoutine(...a),
  deleteRoutine: (...a: unknown[]) => api.deleteRoutine(...a), runRoutineNow: (...a: unknown[]) => api.runRoutineNow(...a),
  listRuns: (...a: unknown[]) => api.listRuns(...a), createRoutine: (...a: unknown[]) => api.createRoutine(...a),
  previewSchedule: (...a: unknown[]) => api.previewSchedule(...a),
}));
vi.mock("../src/hooks/useLiveStore", () => ({ useLiveState: () => ({ routineVersion: { routines: 0 } }) }));

const view = () => render(<MemoryRouter><RoutinesCard botId="bot-1" /></MemoryRouter>);

beforeEach(() => {
  api.listRoutines.mockResolvedValue([routine()]);
  api.listRuns.mockResolvedValue([run(), run({ id: "run-2", state: "expired" }), run({ id: "run-3", state: "error" })]);
});
afterEach(() => { vi.useRealTimers(); cleanup(); Object.values(api).forEach((mock) => mock.mockReset()); });

describe("RoutinesCard", () => {
  it("shows routines with words, next run in words and switch", async () => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date("2026-10-21T05:07:00Z")); // 07:07 Madrid, three hours before
    view();
    expect(await screen.findByText("Morning digest")).toBeInTheDocument();
    expect(screen.getByText("Weekdays at 10:07")).toBeInTheDocument();
    const next = screen.getByText("Next run: in 3 h");
    expect(next).toHaveAttribute("title", "Wed 21 Oct 10:07");
    vi.useRealTimers();
    expect(screen.getByRole("switch", { name: /Morning digest/ })).toHaveAttribute("aria-checked", "true");
    expect(api.listRoutines).toHaveBeenCalledWith("bot-1");
  });

  it("marks a routine that read web content", async () => {
    api.listRoutines.mockResolvedValue([routine({ tainted: true })]);
    view();
    expect(await screen.findByText("from web content")).toBeInTheDocument();
  });

  it("switching off calls PATCH and shows the new state", async () => {
    api.patchRoutine.mockResolvedValue(routine({ enabled: false, next_run_at: null }));
    view();
    await userEvent.click(await screen.findByRole("switch", { name: /Morning digest/ }));
    expect(api.patchRoutine).toHaveBeenCalledWith("r-1", { enabled: false });
    await waitFor(() => expect(screen.getByRole("switch", { name: /Morning digest/ })).toHaveAttribute("aria-checked", "false"));
    expect(screen.queryByText(/^Next:/)).not.toBeInTheDocument();
  });

  it("run now and delete ask first and call the routes", async () => {
    api.runRoutineNow.mockResolvedValue({ run: run() });
    api.deleteRoutine.mockResolvedValue(undefined);
    view();
    await userEvent.click(await screen.findByRole("button", { name: "More for Morning digest" }));
    await userEvent.click(await screen.findByRole("menuitem", { name: "Run now" }));
    expect(api.runRoutineNow).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "Yes, run it now" }));
    expect(api.runRoutineNow).toHaveBeenCalledWith("r-1");

    await userEvent.click(screen.getByRole("button", { name: "More for Morning digest" }));
    await userEvent.click(await screen.findByRole("menuitem", { name: "Delete" }));
    expect(api.deleteRoutine).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "Yes, delete it" }));
    expect(api.deleteRoutine).toHaveBeenCalledWith("r-1");
    await waitFor(() => expect(screen.queryByText("Morning digest")).not.toBeInTheDocument());
  });

  it("says the server's sentence when run now is refused", async () => {
    const { ApiError } = await import("../src/api/client");
    api.runRoutineNow.mockRejectedValue(new ApiError(409, "It's still running."));
    view();
    await userEvent.click(await screen.findByRole("button", { name: "More for Morning digest" }));
    await userEvent.click(await screen.findByRole("menuitem", { name: "Run now" }));
    await userEvent.click(screen.getByRole("button", { name: "Yes, run it now" }));
    expect(await screen.findByText("It's still running.")).toBeInTheDocument();
  });

  it("an old end-of-day summary shows its time only and can be deleted like any routine", async () => {
    api.listRoutines.mockResolvedValue([routine({ id: "b-1", name: "day_summary", builtin: "day_summary", words: "Every day at 21:00", enabled: false, next_run_at: null })]);
    view();
    expect(await screen.findByText("End-of-day summary")).toBeInTheDocument();
    expect(screen.getByText("Every day at 21:00")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "More for End-of-day summary" }));
    expect(await screen.findByRole("menuitem", { name: "Edit" })).toBeInTheDocument();
    api.deleteRoutine.mockResolvedValue(undefined);
    await userEvent.click(screen.getByRole("menuitem", { name: "Delete" }));
    await userEvent.click(screen.getByRole("button", { name: "Yes, delete it" }));
    expect(api.deleteRoutine).toHaveBeenCalledWith("b-1");
  });

  it("history lists the runs in plain words", async () => {
    view();
    await userEvent.click(await screen.findByRole("button", { name: "More for Morning digest" }));
    await userEvent.click(await screen.findByRole("menuitem", { name: "History" }));
    const sheet = await screen.findByRole("dialog");
    expect(await within(sheet).findByText("Done")).toBeInTheDocument();
    expect(within(sheet).getByText("Waited for you")).toBeInTheDocument();
    expect(within(sheet).getByText("Didn't finish")).toBeInTheDocument();
  });

  it("a run with a Report links to it", async () => {
    api.listRuns.mockResolvedValue([run({ report_message_id: "m-9" })]);
    view();
    await userEvent.click(await screen.findByRole("button", { name: "More for Morning digest" }));
    await userEvent.click(await screen.findByRole("menuitem", { name: "History" }));
    expect(await screen.findByRole("link", { name: "See the Report" })).toBeInTheDocument();
  });

  it("history leads with the routine's last error and its time (self-healing, 2026-11-10)", async () => {
    api.listRoutines.mockResolvedValue([routine({ last_error: { kind: "no_answer", at: "2026-10-20T10:40:00Z" } })]);
    view();
    await userEvent.click(await screen.findByRole("button", { name: "More for Morning digest" }));
    await userEvent.click(await screen.findByRole("menuitem", { name: "History" }));
    const sheet = await screen.findByRole("dialog");
    expect(await within(sheet).findByRole("status")).toHaveTextContent(/^Couldn't check \(computer didn't answer\) · .*12:40$/);
  });
});
