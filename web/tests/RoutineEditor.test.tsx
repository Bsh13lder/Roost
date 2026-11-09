import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { RoutineEditor } from "../src/components/routines/RoutineEditor";
import { ApiError } from "../src/api/client";
import { routine } from "./routineFixtures";
import { setAppTimeZone } from "../src/lib/timeZone";

const api = { createRoutine: vi.fn(), patchRoutine: vi.fn(), previewSchedule: vi.fn() };
vi.mock("../src/api/routines", () => ({
  createRoutine: (...a: unknown[]) => api.createRoutine(...a), patchRoutine: (...a: unknown[]) => api.patchRoutine(...a),
  previewSchedule: (...a: unknown[]) => api.previewSchedule(...a),
}));

const standing = { listPermissions: vi.fn() };
vi.mock("../src/api/standing", () => ({ listPermissions: (...a: unknown[]) => standing.listPermissions(...a) }));

afterEach(() => { cleanup(); Object.values(api).forEach((mock) => mock.mockReset()); standing.listPermissions.mockReset(); });

const PREVIEW = { words: "Weekdays at 09:00", next: ["2026-10-21T09:00:00+02:00", "2026-10-22T09:00:00+02:00"] };

describe("RoutineEditor", () => {
  it("the editor switches Times and Custom and shows the live preview", async () => {
    api.previewSchedule.mockResolvedValue(PREVIEW);
    render(<RoutineEditor botId="bot-1" routine={null} onClose={vi.fn()} onSaved={vi.fn()} />);
    expect(await screen.findByText("Wed 21 Oct 09:00")).toBeInTheDocument();
    expect(screen.getByText("Times are in Madrid time.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Mon" })).toHaveAttribute("aria-pressed", "true");
    await userEvent.click(screen.getByRole("button", { name: "Custom" }));
    const cron = screen.getByLabelText("Cron");
    api.previewSchedule.mockResolvedValue({ words: "Every day at 08:00", next: ["2026-10-22T08:00:00+02:00"] });
    fireEvent.change(cron, { target: { value: "0 8 * * *" } });
    expect(await screen.findByText("Every day at 08:00")).toBeInTheDocument();
    await waitFor(() => expect(api.previewSchedule).toHaveBeenLastCalledWith({ kind: "cron", expr: "0 8 * * *" }));
    await userEvent.click(screen.getByRole("button", { name: "Times" }));
    expect(screen.getByRole("button", { name: "Tue" })).toBeInTheDocument();
  });

  it("a bad schedule shows the server's sentence", async () => {
    api.previewSchedule.mockRejectedValue(new ApiError(422, "That custom schedule isn't valid."));
    render(<RoutineEditor botId="bot-1" routine={null} onClose={vi.fn()} onSaved={vi.fn()} />);
    await userEvent.click(screen.getByRole("button", { name: "Custom" }));
    fireEvent.change(screen.getByLabelText("Cron"), { target: { value: "nonsense" } });
    expect(await screen.findByText("That custom schedule isn't valid.")).toBeInTheDocument();
  });

  it("saving a new routine sends it and reports it; a refusal shows the sentence", async () => {
    api.previewSchedule.mockResolvedValue(PREVIEW);
    api.createRoutine.mockRejectedValueOnce(new ApiError(422, "A routine needs a name."));
    const onSaved = vi.fn();
    render(<RoutineEditor botId="bot-1" routine={null} onClose={vi.fn()} onSaved={onSaved} />);
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByText("A routine needs a name.")).toBeInTheDocument();
    api.createRoutine.mockResolvedValue(routine());
    await userEvent.type(screen.getByLabelText("Name"), "Digest");
    await userEvent.type(screen.getByLabelText("What to do"), "Summarise");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(onSaved).toHaveBeenCalled());
    expect(api.createRoutine).toHaveBeenLastCalledWith("bot-1", {
      name: "Digest", instructions: "Summarise", schedule: { kind: "times", days: [1, 2, 3, 4, 5], times: ["09:00"] },
    });
  });

  it("the built-in hides delete and instructions", async () => {
    api.previewSchedule.mockResolvedValue(PREVIEW);
    api.patchRoutine.mockResolvedValue(routine());
    render(<RoutineEditor botId="bot-1" routine={routine({ builtin: "day_summary", name: "day_summary" })} onClose={vi.fn()} onSaved={vi.fn()} />);
    expect(screen.queryByLabelText("What to do")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Name")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Delete/ })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(api.patchRoutine).toHaveBeenCalledWith("r-1", { schedule: { kind: "times", days: [1, 2, 3, 4, 5], times: ["10:07"] } });
  });

  it("an existing routine shows its standing permission; the built-in and a new one do not", async () => {
    api.previewSchedule.mockResolvedValue(PREVIEW);
    standing.listPermissions.mockResolvedValue([]);
    render(<RoutineEditor botId="bot-1" routine={routine()} onClose={vi.fn()} onSaved={vi.fn()} />);
    expect(await screen.findByRole("heading", { name: "Standing permission" })).toBeInTheDocument();
    expect(standing.listPermissions).toHaveBeenCalledWith("r-1");
    cleanup();
    render(<RoutineEditor botId="bot-1" routine={null} onClose={vi.fn()} onSaved={vi.fn()} />);
    expect(screen.queryByRole("heading", { name: "Standing permission" })).not.toBeInTheDocument();
  });
});

// The account's zone (owner, 2026-11-09): the preview says which clock its times are on.
describe("RoutineEditor on another zone", () => {
  it("shows the next runs on the account's clock and names its city", async () => {
    setAppTimeZone("America/New_York");
    api.previewSchedule.mockResolvedValue(PREVIEW);
    render(<RoutineEditor botId="bot-1" routine={null} onClose={vi.fn()} onSaved={vi.fn()} />);
    expect(await screen.findByText("Wed 21 Oct 03:00")).toBeInTheDocument();
    expect(screen.getByText("Times are in New York time.")).toBeInTheDocument();
  });
});
